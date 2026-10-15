-- 038_community_dollar_minimum_and_member_count.sql  (LOCAL-704, D665 / D666)
--
-- Every community member pays at least $1 to join, and every community shows
-- its member count. No more free communities. After launch, a community that
-- drops below 2 active members gets weekly warnings and is archived only after
-- a full week at 0 members. Purely ADDITIVE and idempotent, wrapped in one
-- transaction. Applying twice is a no-op (INSERT ... ON CONFLICT / ADD COLUMN
-- IF NOT EXISTS / value-asserting backfill). NO DROP, NO column retype.
--
-- THE RULES (D665 + addendum, D666):
--
--   * D665: a $1 pass (audioura.pass.usd1) joins the pass catalogue — the
--     commitment-fee floor. The create form has no "Free" option; every
--     community is paid. Existing FREE communities (the demo book club) are
--     converted to paid with a $1 / month option; their current (free) members
--     are grandfathered — their membership is given a 30-day expiry FROM THIS
--     MIGRATION, after which they need a pass like everyone else.
--   * D665 addendum: the organiser is NOT a member — never in member_count or
--     the launch bar; the server rejects an owner buying/joining their own
--     community (409 owner_cannot_join). No schema change for that (it is a
--     membership row that simply must never exist for the owner); this
--     migration cleans up any owner self-membership that a pre-rule build may
--     have written, so the member_count and launch bar start correct.
--   * D666: once launched, an active member is one with an unexpired PAID pass
--     (owner excluded). Below 2 → the organiser + members are warned the same
--     day, then weekly, until back to >= 2. At 0 active members for 7
--     consecutive days → archived (reason 'no_members'). Three new columns
--     track this; the launch-window job uses them.
--
-- WHAT THIS ADDS:
--   1. community_pass_products: the '$1' row (re-asserted; 029 also seeds it so
--      a fresh DB has it).
--   2. communities.low_members_since     — when the active count last dropped
--                                            below 2 (NULL while >= 2). Drives
--                                            the "day 0 then weekly" warnings.
--   3. communities.last_low_warning_at    — when the last low-members warning
--                                            was sent (NULL = none yet). Guards
--                                            the weekly cadence.
--   4. communities.zero_members_since     — when the active count last hit 0
--                                            (NULL while >= 1). At 7 days → the
--                                            community is archived ('no_members').
--   5. archived_reason gains 'no_members' in its CHECK domain.
--   6. The demo book club (and any other free community) → is_paid, a $1/month
--      pass option, current members grandfathered 30 days.

BEGIN;

-- ─── 1. The $1 commitment-fee pass (D665). Idempotent re-assert. ─────────────
INSERT INTO community_pass_products (product_id, price_usd, label) VALUES
    ('audioura.pass.usd1', 1.00, '$1')
ON CONFLICT (product_id) DO UPDATE SET
    price_usd = EXCLUDED.price_usd,
    label     = EXCLUDED.label,
    active    = TRUE;

-- ─── 2-4. Post-launch low-member tracking columns (D666) ─────────────────────
ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS low_members_since TIMESTAMPTZ;

ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS last_low_warning_at TIMESTAMPTZ;

ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS zero_members_since TIMESTAMPTZ;

-- ─── 5. Widen the archived_reason domain to include 'no_members' (D666) ──────
-- The constraint was added by migration 037. Drop + re-add it (guarded) so the
-- domain gains 'no_members'. Idempotent: if the constraint already allows
-- 'no_members' (a re-run) the DROP/ADD simply restores the same shape.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_communities_archived_reason'
          AND conrelid = 'communities'::regclass
    ) THEN
        ALTER TABLE communities DROP CONSTRAINT chk_communities_archived_reason;
    END IF;
    ALTER TABLE communities
        ADD CONSTRAINT chk_communities_archived_reason
        CHECK (archived_reason IS NULL
               OR archived_reason IN ('launch_window_missed',
                                      'handover_expired',
                                      'no_members'));
END $$;

-- The low-members / zero-members job scans communities by these timestamps; a
-- partial index keeps the scan cheap (only communities currently below the bar
-- carry a non-NULL low_members_since).
CREATE INDEX IF NOT EXISTS idx_communities_low_members
    ON communities (low_members_since)
    WHERE low_members_since IS NOT NULL;

-- ─── 6. The owner is NOT a member (D665 addendum): clean up any owner self- ──
-- membership a pre-rule build may have written, so member_count and the launch
-- bar start correct. A fresh DB has none; harmless no-op there.
DELETE FROM community_memberships m
    USING communities c
    WHERE m.community_id = c.id
      AND m.user_id = c.owner_user_id;

-- ─── 6. Convert existing FREE communities to paid $1/month (D665) ────────────
-- Every remaining free community (is_paid = FALSE) becomes paid. This covers
-- the demo book club (id 1) and any other free community created before the
-- rule. Each gets:
--   (a) is_paid = TRUE;
--   (b) a $1 / month pass option (audioura.pass.usd1, 30 days) if it has no
--       pass option yet;
--   (c) its current members (free joins: expires_at IS NULL) grandfathered —
--       expires_at = NOW() + 30 days, so they keep access for a month and then
--       need a pass. transaction_id stays NULL (they never paid), so they do
--       NOT count toward the paid launch bar — a grandfathered free member is
--       not a committed paid member.
--
-- Idempotent: a community already paid is skipped by the WHERE; the pass option
-- insert is ON CONFLICT DO NOTHING; the grandfather only touches rows still at
-- NULL expiry (a re-run finds none, because the first run set them 30 days out).

-- (b) add a $1/month option to every currently-free community that lacks one.
INSERT INTO community_passes (community_id, product_id, length, duration_days)
    SELECT c.id, 'audioura.pass.usd1', 'month', 30
    FROM communities c
    WHERE c.is_paid = FALSE
    ON CONFLICT (community_id, product_id, length) DO NOTHING;

-- (c) grandfather current free members: give the free (NULL-expiry) memberships
-- of a currently-free community a 30-day expiry from now. Do this BEFORE
-- flipping is_paid so the "currently free" set is unambiguous.
UPDATE community_memberships m
    SET expires_at = NOW() + INTERVAL '30 days', updated_at = NOW()
    FROM communities c
    WHERE m.community_id = c.id
      AND c.is_paid = FALSE
      AND m.expires_at IS NULL;

-- (a) flip every free community to paid.
UPDATE communities
    SET is_paid = TRUE, updated_at = NOW()
    WHERE is_paid = FALSE;

COMMENT ON COLUMN communities.low_members_since IS
    'LOCAL-704/D666: when the active member count (unexpired paid passes, owner '
    'excluded) last dropped below 2. NULL while >= 2. Drives the day-0-then-'
    'weekly low-members warnings.';
COMMENT ON COLUMN communities.last_low_warning_at IS
    'LOCAL-704/D666: when the last low-members warning was sent. NULL = none '
    'yet. Guards the weekly cadence so a warning fires at most once per 7 days.';
COMMENT ON COLUMN communities.zero_members_since IS
    'LOCAL-704/D666: when the active member count last hit 0. NULL while >= 1. '
    'At 7 consecutive days the launch-window job archives the community with '
    'reason no_members.';
COMMENT ON COLUMN communities.archived_reason IS
    'LOCAL-703/704 / D664/D666: why a community was archived — '
    'launch_window_missed (missed the first-two-members bar), handover_expired '
    '(LOCAL-702 30-day hand-over path), or no_members (7 days at 0 active '
    'members after launch). NULL when not archived.';

COMMIT;
