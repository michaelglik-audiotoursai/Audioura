-- 047_reimbursement.sql  (LOCAL-729, D691 / D690 / D692 / D688 / D660 / D613)
--
-- Reimbursement, ADMINISTRATOR ONLY (ClickUp wdvrdaz3tb, approved by Michael
-- 2026-10-21). Only Audioura (Michael, through LEAD) reimburses a tour buyer, a
-- community member or a plan purchaser — never an app user. The actions reuse
-- the LOCAL-728 admin_actions ledger (migration 046) so EVERY reimbursement is
-- one audit row, next to the bar/ban rows. No purchase-bearing row is ever
-- deleted (D690): a money refund revokes by the existing void/flag path and the
-- receipt row stays.
--
-- This migration is PURELY ADDITIVE and idempotent: NO DROP of a column, NO
-- DELETE of a row, NO column retype. ADD COLUMN IF NOT EXISTS / CREATE TABLE IF
-- NOT EXISTS, and ONE guarded CHECK widen that only ever GROWS the allowed set
-- (so no existing admin_actions row can be invalidated). Applying it twice is a
-- no-op. Row counts before/after are identical for every existing table — it
-- adds tables/columns only, never data rows.
--
-- Four additive pieces:
--
-- 1. admin_actions.action — widen the CHECK to the SUPERSET  ─────────────────
--    046 constrained action to the six moderation verbs. Reimbursement adds
--    seven more: 'refund_google', 'apple_refund_support', 'grant_tour',
--    'extend_pass', 'grant_pass', 'add_plan_units', 'extend_plan'. We drop the
--    046 constraint and re-add the SUPERSET (all thirteen). Dropping+re-adding a
--    CHECK touches no row; the new set contains the old, so every existing row
--    still satisfies it. Guarded so a re-run is inert.
--
-- 2. admin_actions — money + purchase link columns  ─────────────────────────
--    A reimbursement row records WHAT was given or refunded against WHICH
--    purchase: amount_usd (money refunds A/B), transaction_id (the store order /
--    transaction id — Apple "Order ID" / Google "GPA."), store, and target_tour_id
--    (a grant-tour's tour). All nullable; a moderation row (bar/ban) leaves them
--    NULL, unchanged from 046.
--
-- 3. support_ids — the public Support ID per device (D692/§3 of the design)  ─
--    A short public alias of the device, e.g. 'AU-7K3Q', shown in About with a
--    Copy button and resolvable by the admin tools. NEVER the secret device id
--    (users.secret_id / device user_id). One alias per device (user_id UNIQUE),
--    unique across devices (support_id UNIQUE), collision-safe generation in
--    support_id.py. A buyer gives their Support ID (or a store order number) so
--    we find them without asking for private data.
--
-- 4. purchases.refund_supported — the Apple "we support it" flag  ────────────
--    Apple refunds its own IAPs; we cannot send money on iPhone (design §1).
--    `apple-refund-message` prints the ready-to-send customer text pointing at
--    reportaproblem.apple.com AND marks the purchase refund_supported = TRUE, so
--    the consumption answer (App Store Server Notifications, wdvrdaz2zf — a
--    SEPARATE task) can tell Apple we support the refund. A boolean, default
--    FALSE for every existing row; flipping it grants/refunds nothing by itself.

BEGIN;

-- ─── 1. Widen admin_actions.action to the reimbursement superset ─────────────
DO $$
BEGIN
    -- Drop the 046 six-verb CHECK if present (its auto-generated name is the
    -- column-check default 'admin_actions_action_check').
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'admin_actions_action_check'
          AND conrelid = 'admin_actions'::regclass
    ) THEN
        ALTER TABLE admin_actions DROP CONSTRAINT admin_actions_action_check;
    END IF;
    -- Add the SUPERSET constraint if it is not already present.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_admin_actions_action'
          AND conrelid = 'admin_actions'::regclass
    ) THEN
        ALTER TABLE admin_actions
            ADD CONSTRAINT chk_admin_actions_action
            CHECK (action IN (
                -- LOCAL-728 moderation verbs (unchanged set)
                'bar', 'unbar', 'ban', 'unban',
                'disable_community', 'enable_community',
                -- LOCAL-729 reimbursement verbs (added)
                'refund_google', 'apple_refund_support', 'grant_tour',
                'extend_pass', 'grant_pass', 'add_plan_units', 'extend_plan'));
    END IF;
END$$;

-- ─── 2. Money + purchase-link columns on admin_actions ───────────────────────
ALTER TABLE admin_actions
    ADD COLUMN IF NOT EXISTS amount_usd      NUMERIC(10,2);
ALTER TABLE admin_actions
    ADD COLUMN IF NOT EXISTS transaction_id  VARCHAR(255);
ALTER TABLE admin_actions
    ADD COLUMN IF NOT EXISTS store           VARCHAR(20);
ALTER TABLE admin_actions
    ADD COLUMN IF NOT EXISTS target_tour_id  INTEGER;

COMMENT ON COLUMN admin_actions.amount_usd IS
    'LOCAL-729: the USD amount of a MONEY refund (refund_google full/partial). '
    'NULL for a make-good-in-kind or moderation row.';
COMMENT ON COLUMN admin_actions.transaction_id IS
    'LOCAL-729: the store order/transaction id a reimbursement answers (Google '
    'orderId / Apple Order ID), for the paper trail. NULL for a plain grant.';
COMMENT ON COLUMN admin_actions.store IS
    'LOCAL-729: the store of the reimbursed purchase (apple|google|stub) when a '
    'reimbursement targets one. NULL otherwise.';
COMMENT ON COLUMN admin_actions.target_tour_id IS
    'LOCAL-729: the tour a grant_tour re-granted (an audio_tours.id). NULL for '
    'non-tour actions.';

-- The device-history read (ledger --device <support-id|device>) filters by the
-- target user; the 046 idx_admin_actions_target_user already serves it. A tour
-- lookup is rare and small, so no new index is needed.

-- ─── 3. support_ids — public Support ID alias per device ─────────────────────
CREATE TABLE IF NOT EXISTS support_ids (
    -- The public alias shown in About (e.g. 'AU-7K3Q'). Unique across devices.
    -- Generation is collision-safe in support_id.py (retry on conflict).
    support_id   VARCHAR(16) PRIMARY KEY,
    -- The device it aliases (users.secret_id / the device user_id). One alias
    -- per device: UNIQUE so a device never gets two Support IDs.
    user_id      VARCHAR(255) NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE support_ids IS
    'LOCAL-729/D692: the public Support ID (e.g. AU-7K3Q), a short alias of a '
    'device shown in About with a Copy button and resolvable by the admin '
    'reimbursement tools. NEVER the secret device id. One alias per device '
    '(user_id UNIQUE), unique across devices (support_id PK). Additive, '
    'collision-safe generation (support_id.py).';

-- ─── 4. purchases.refund_supported — the Apple "we support it" flag ──────────
ALTER TABLE purchases
    ADD COLUMN IF NOT EXISTS refund_supported BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN purchases.refund_supported IS
    'LOCAL-729/D692: TRUE when the admin ran apple-refund-message for this '
    'purchase — Audioura supports the buyer''s Apple refund. The consumption '
    'answer (App Store Server Notifications, wdvrdaz2zf) reads this. Grants/'
    'refunds nothing by itself; default FALSE for every existing row.';

COMMIT;
