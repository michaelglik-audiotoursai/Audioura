-- Migration 006: Wallet Ledger for user-facing billing (LOCAL-66)
-- 
-- This is the USER-FACING money record. cost_ledger (005) is what things cost US;
-- wallet_ledger is what the USER is charged and what they hold.
--
-- Append-only. One row per movement: top-up, charge, refund clawback, monthly fee.
-- Never mutate a row; corrections are new rows.
-- Money stored as integer cents — never float.
--
-- Balance is DERIVED from the ledger (SUM of amount_cents), not a mutable field.
-- A cached balance column exists for read performance but is rebuildable.
--
-- Refund clawbacks may drive the balance negative. Record it; do not clamp.
-- Losing the record is the failure mode.
--
-- Every write carries a caller-supplied idempotency key to prevent double-credit.

BEGIN;

-- The append-only ledger
CREATE TABLE IF NOT EXISTS wallet_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(128) NOT NULL,
    movement_type VARCHAR(64) NOT NULL,
    amount_cents INTEGER NOT NULL,  -- positive = credit, negative = debit
    balance_after_cents INTEGER NOT NULL,  -- derived snapshot for auditability
    idempotency_key VARCHAR(256) NOT NULL,
    description TEXT,
    reference_id VARCHAR(256),  -- job_id, subscription_id, or payment_id
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotency: each key must be unique to prevent double-credit
CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ledger_idempotency
ON wallet_ledger (idempotency_key);

-- User's transaction history, newest first
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_time
ON wallet_ledger (user_id, created_at DESC);

-- Lookup by reference (e.g., find all movements for a job)
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_reference
ON wallet_ledger (reference_id);

-- Cached balance for fast reads (rebuildable from ledger)
CREATE TABLE IF NOT EXISTS wallet_balance_cache (
    user_id VARCHAR(128) PRIMARY KEY,
    balance_cents INTEGER NOT NULL DEFAULT 0,
    last_ledger_id UUID,  -- last wallet_ledger row incorporated
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- User subscription state (for unlimited tier cost-stop tracking)
-- Note: This is a MINIMAL tracking table. Full subscription lifecycle
-- (PaymentProvider, RevenueCat integration) is LOCAL-61's scope.
CREATE TABLE IF NOT EXISTS wallet_subscription (
    user_id VARCHAR(128) PRIMARY KEY,
    tier VARCHAR(32) NOT NULL DEFAULT 'free',  -- free, pay_per_use, unlimited
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    monthly_cost_spent_cents INTEGER NOT NULL DEFAULT 0,  -- for unlimited tier cost-stop
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE wallet_ledger IS 'Append-only user wallet ledger. One row per money movement. Never mutate rows.';
COMMENT ON COLUMN wallet_ledger.movement_type IS 'topup, charge, refund_clawback, monthly_fee, monthly_fee_unlimited';
COMMENT ON COLUMN wallet_ledger.amount_cents IS 'Positive = credit to user (topup, refund). Negative = debit (charge, fee, clawback).';
COMMENT ON COLUMN wallet_ledger.balance_after_cents IS 'Running balance snapshot after this movement. Matches SUM(amount_cents) up to this row.';
COMMENT ON COLUMN wallet_ledger.idempotency_key IS 'Caller-supplied. Duplicate key = reject (idempotent retry safety).';
COMMENT ON TABLE wallet_balance_cache IS 'Cached balance for fast reads. Rebuildable from wallet_ledger at any time.';
COMMENT ON TABLE wallet_subscription IS 'User subscription tier. Minimal — full lifecycle in LOCAL-61.';

COMMIT;
