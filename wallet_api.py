"""
Wallet API — HTTP endpoints for the Flutter Wallet screen.
===========================================================
Implements the contract that LOCAL-62 mocked:

    GET  /wallet/<user_id>
    GET  /wallet/<user_id>/transactions?limit=50
    GET  /plans/available
    POST /wallet/<user_id>/topup   {product_id}

Hosted on the tour_orchestrator (port 5002) because:
    - The Flutter app already routes wallet calls to Service.orchestrator
    - The orchestrator is in docker-compose and talks to the DB
    - No new service created (as required)

This module is a Flask Blueprint, registered by the orchestrator.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from flask import Blueprint, request, jsonify

import psycopg2
import psycopg2.extras

from wallet_ledger import (
    get_balance_cents,
    topup as wallet_topup,
    get_transaction_history,
    check_unlimited_cost_stop,
    check_low_balance,
    CREDIT_TOPUP_USD,
    UNLIMITED_COST_STOP_USD,
    _get_db_connection,
    _ensure_tables,
)
from pricing import compute_user_charge

logger = logging.getLogger(__name__)

wallet_bp = Blueprint("wallet", __name__)

# ---------------------------------------------------------------------------
# Configuration — plans from env/config, never hardcoded in UI
# ---------------------------------------------------------------------------

def _get_plans_config() -> list:
    """Return available plans from configuration.
    Prices come from config — the API is the single source.
    """
    ppu_fee = os.environ.get("PPU_MONTHLY_FEE_USD", "2.00")
    unlimited_fee = os.environ.get("UNLIMITED_MONTHLY_FEE_USD", "50.00")

    return [
        {
            "plan_id": "free",
            "display_name": "Free",
            "price_usd": 0.0,
            "period": "forever",
            "features": [
                "Browse pre-made tours",
                "Limited tour downloads",
            ],
        },
        {
            "plan_id": "pay_per_use",
            "display_name": "Pay-Per-Use",
            "price_usd": float(ppu_fee),
            "period": "month",
            "features": [
                "Unlimited tour generation",
                "Unlimited news articles",
                "Pay only for what you use",
                "Credits never expire",
            ],
        },
        {
            "plan_id": "unlimited",
            "display_name": "Unlimited",
            "price_usd": float(unlimited_fee),
            "period": "month",
            "features": [
                "Unlimited tour generation",
                "Unlimited news articles",
                "No per-use charges",
                "Priority processing",
                "All future features included",
            ],
        },
    ]


def _get_user_tier(user_id: str) -> str:
    """Read the user's current subscription tier from wallet_subscription."""
    conn = _get_db_connection()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tier FROM wallet_subscription WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
        return "free"
    except Exception as e:
        logger.error(f"[WALLET_API] _get_user_tier failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return "free"


def _get_subscription_period(user_id: str) -> tuple:
    """Get the current subscription billing period (period_start, period_end).
    Falls back to current calendar month if no subscription row exists.
    """
    conn = _get_db_connection()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT period_start, period_end FROM wallet_subscription WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.close()

        if row and row[0] and row[1]:
            return row[0], row[1]

        # Default: current calendar month
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)
        return period_start, period_end

    except Exception as e:
        logger.error(f"[WALLET_API] _get_subscription_period failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)
        return period_start, period_end


def _get_period_spend_usd(user_id: str, period_start: datetime) -> float:
    """Sum of user charges (debit movements) in the current billing period."""
    conn = _get_db_connection()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(ABS(amount_cents)), 0)
                FROM wallet_ledger
                WHERE user_id = %s
                  AND movement_type = 'charge'
                  AND created_at >= %s
                """,
                (user_id, period_start),
            )
            total_cents = cur.fetchone()[0]
        conn.close()
        return total_cents / 100.0
    except Exception as e:
        logger.error(f"[WALLET_API] _get_period_spend_usd failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return 0.0


# ---------------------------------------------------------------------------
# GET /wallet/<user_id>
# ---------------------------------------------------------------------------

@wallet_bp.route("/wallet/<user_id>", methods=["GET"])
def get_wallet(user_id: str):
    """Get wallet summary for the specified user.

    Response contract (field names are the API contract — do NOT rename):
    {
        "plan": "free" | "pay_per_use" | "unlimited",
        "balance_usd": float,
        "period_spend_usd": float,
        "period_start": ISO8601 string,
        "period_end": ISO8601 string,
        "cost_stop_progress": {"used_usd": float, "limit_usd": float} | null,
        "low_balance": bool
    }
    """
    try:
        tier = _get_user_tier(user_id)
        balance_cents = get_balance_cents(user_id)
        balance_usd = balance_cents / 100.0
        period_start, period_end = _get_subscription_period(user_id)
        period_spend_usd = _get_period_spend_usd(user_id, period_start)

        # cost_stop_progress: null for free and ppu, populated only for unlimited
        cost_stop_progress = None
        if tier == "unlimited":
            cost_stop_info = check_unlimited_cost_stop(user_id)
            cost_stop_progress = {
                "used_usd": float(cost_stop_info["current_cost_usd"]),
                "limit_usd": float(cost_stop_info["limit_usd"]),
            }

        # low_balance: only meaningful for pay_per_use
        low_balance = False
        if tier == "pay_per_use":
            low_balance = check_low_balance(user_id) is not None

        response = {
            "plan": tier,
            "balance_usd": round(balance_usd, 2),
            "period_spend_usd": round(period_spend_usd, 2),
            "period_start": period_start.isoformat() if hasattr(period_start, 'isoformat') else str(period_start),
            "period_end": period_end.isoformat() if hasattr(period_end, 'isoformat') else str(period_end),
            "cost_stop_progress": cost_stop_progress,
            "low_balance": low_balance,
        }

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"[WALLET_API] GET /wallet/{user_id} failed: {e}")
        return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# GET /wallet/<user_id>/transactions?limit=50
# ---------------------------------------------------------------------------

@wallet_bp.route("/wallet/<user_id>/transactions", methods=["GET"])
def get_transactions(user_id: str):
    """Get transaction history for the specified user.

    Response contract (list of):
    {
        "id": string,
        "created_at": ISO8601 string,
        "operation_type": string,
        "description": string,
        "charged_usd": float,
        "cache_hit": bool
    }
    """
    try:
        limit = request.args.get("limit", 50, type=int)
        limit = min(max(limit, 1), 200)  # clamp 1..200

        conn = _get_db_connection()
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT wl.id, wl.created_at, wl.movement_type, wl.description,
                       wl.amount_cents, wl.reference_id
                FROM wallet_ledger wl
                WHERE wl.user_id = %s
                ORDER BY wl.created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()

            # For each transaction that references a cost_ledger job, check cache_hit
            # We join against cost_ledger to get the cache_hit flag
            reference_ids = [r[5] for r in rows if r[5]]
            cache_hit_map = {}
            if reference_ids:
                cur.execute(
                    """
                    SELECT job_id, cache_hit
                    FROM cost_ledger
                    WHERE job_id = ANY(%s)
                    """,
                    (reference_ids,),
                )
                for job_row in cur.fetchall():
                    cache_hit_map[job_row[0]] = job_row[1]

        conn.close()

        transactions = []
        for row in rows:
            row_id, created_at, movement_type, description, amount_cents, reference_id = row

            # Determine operation_type from movement_type
            # The movement_type maps: charge -> operation from cost_ledger,
            # topup -> "topup", monthly_fee -> "monthly_fee", etc.
            operation_type = movement_type

            # For charges, try to get the actual operation type from cost_ledger
            cache_hit = False
            if movement_type == "charge" and reference_id:
                cache_hit = cache_hit_map.get(reference_id, False)
                # Also try to get more specific operation_type from cost_ledger
                # But the description already comes from pricing.py

            # charged_usd: the absolute amount (positive for debits shown to user)
            # For credits (topup), show as negative per the Flutter mock convention
            if movement_type in ("topup",):
                charged_usd = -(abs(amount_cents) / 100.0)
            else:
                charged_usd = abs(amount_cents) / 100.0

            # Cache-hit charges are $0.00 with cache_hit: true
            if cache_hit:
                charged_usd = 0.00

            transactions.append({
                "id": str(row_id),
                "created_at": created_at.isoformat() if created_at else None,
                "operation_type": operation_type,
                "description": description or _fallback_description(movement_type),
                "charged_usd": round(charged_usd, 2),
                "cache_hit": cache_hit,
            })

        return jsonify(transactions), 200

    except Exception as e:
        logger.error(f"[WALLET_API] GET /wallet/{user_id}/transactions failed: {e}")
        return jsonify({"error": "Internal server error"}), 500


def _fallback_description(movement_type: str) -> str:
    """Provide a human-readable fallback description."""
    labels = {
        "topup": "Credit top-up",
        "charge": "Usage charge",
        "refund_clawback": "Refund processed",
        "monthly_fee": "Monthly subscription fee",
        "monthly_fee_unlimited": "Unlimited monthly fee",
    }
    return labels.get(movement_type, movement_type.replace("_", " ").title())


# ---------------------------------------------------------------------------
# GET /plans/available
# ---------------------------------------------------------------------------

@wallet_bp.route("/plans/available", methods=["GET"])
def get_available_plans():
    """Get all available subscription plans.

    Response contract (list of):
    {
        "plan_id": string,
        "display_name": string,
        "price_usd": float,
        "period": string,
        "features": [string, ...]
    }
    """
    return jsonify(_get_plans_config()), 200


# ---------------------------------------------------------------------------
# POST /wallet/<user_id>/topup   {product_id}
# ---------------------------------------------------------------------------

@wallet_bp.route("/wallet/<user_id>/topup", methods=["POST"])
def topup_wallet(user_id: str):
    """Process a credit top-up.

    Idempotent: uses product_id as part of the idempotency key.
    A retried call with the same product_id must not double-credit.

    Request body:
        {"product_id": string}

    Response contract:
        {"status": "success", "new_balance_usd": float}
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        product_id = data.get("product_id")

        if not product_id:
            return jsonify({"error": "product_id is required"}), 400

        # The idempotency key is derived from user_id + product_id.
        # This makes the same (user, product) purchase idempotent.
        # In production, product_id would come from RevenueCat/App Store
        # and be unique per purchase (receipt ID).
        idempotency_key = f"topup:{user_id}:{product_id}"

        row_id, new_balance_cents = wallet_topup(
            user_id=user_id,
            amount_usd=CREDIT_TOPUP_USD,
            idempotency_key=idempotency_key,
            payment_id=product_id,
        )

        new_balance_usd = new_balance_cents / 100.0

        return jsonify({
            "status": "success",
            "new_balance_usd": round(new_balance_usd, 2),
        }), 200

    except Exception as e:
        logger.error(f"[WALLET_API] POST /wallet/{user_id}/topup failed: {e}")
        return jsonify({"error": "Internal server error"}), 500
