-- 046_admin_moderation.sql  (LOCAL-728, D691 / D690 / D658)
--
-- Admin-only moderation. Under D691 only the ADMINISTRATOR (Michael, through
-- LEAD) bars a member from a community or bans a user from the service; members
-- and organisers only report. This migration adds the stores the admin CLI
-- (moderation.py) and the admin-key endpoints write to. PURELY ADDITIVELY and
-- idempotently: NO DROP, NO DELETE, NO column retype. Applying twice is a no-op.
-- It adds TABLES/COLUMNS only, never data rows — row counts before/after are
-- identical for every existing table.
--
-- Three additive pieces:
--
-- 1. community_blocks.kind gains 'admin_bar'  ───────────────────────────────
--    community_blocks (migration 044) constrains kind to
--    ('member_block','organiser_bar'). D691 removes user-level blocking; the
--    admin bar reuses the same table with a THIRD kind, 'admin_bar': the
--    administrator bars a member from one community. The bar ENDS the
--    membership by expiry (never DELETE — D690: the row is the purchase record)
--    and stops a rejoin by code. The existing member_block/organiser_bar rows
--    (should be 0) are left untouched as history. We widen the CHECK additively
--    by dropping the old constraint and adding the superset — the set of
--    allowed values only GROWS, so no existing row can be invalidated.
--
-- 2. service_bans  ──────────────────────────────────────────────────────────
--    A user banned from the service (D658): no purchases, no generation, no
--    community joins or creation. Their DOWNLOADED audio stays on the device
--    (D658 — the server never deletes it; a ban only blocks NEW access). A ban
--    is one row per user; lifting it sets lifted_at (the row is kept as
--    history, never deleted). The gate reads "is there a ban for this user with
--    lifted_at IS NULL?".
--
-- 3. admin_actions  ─────────────────────────────────────────────────────────
--    The ledger: EVERY admin moderation action (bar, ban, disable a community,
--    and every lift) writes one row — who did it, when, the target, the reason,
--    and the report id it answers (when any). Append-only; nothing here is ever
--    updated or deleted. This is the audit trail D691 requires ("every action
--    is written to an admin_actions ledger").

BEGIN;

-- ─── 1. Allow kind = 'admin_bar' on community_blocks ─────────────────────────
-- Widen the CHECK to the SUPERSET. Dropping + re-adding the constraint does not
-- touch any row; the new set contains the old, so every existing row still
-- satisfies it. Guarded so a re-run (constraint already the superset) is inert.
DO $$
BEGIN
    -- Drop the old 044 constraint if it is still the two-value form.
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'community_blocks_kind_check'
    ) THEN
        ALTER TABLE community_blocks DROP CONSTRAINT community_blocks_kind_check;
    END IF;
    -- Add the superset constraint if it is not already present.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_community_blocks_kind'
    ) THEN
        ALTER TABLE community_blocks
            ADD CONSTRAINT chk_community_blocks_kind
            CHECK (kind IN ('member_block', 'organiser_bar', 'admin_bar'));
    END IF;
END$$;

-- ─── 2. service_bans — a user banned from the whole service (D658) ──────────
CREATE TABLE IF NOT EXISTS service_bans (
    id            SERIAL PRIMARY KEY,
    user_id       VARCHAR(255) NOT NULL,
    reason        TEXT,
    -- The report this ban answers, when it came from one (FK kept soft: a
    -- report may be deleted-by-community-cascade later; SET NULL keeps the ban).
    report_id     INTEGER,
    banned_by     VARCHAR(255),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A lifted ban keeps its row (history); lifted_at IS NULL means active.
    lifted_at     TIMESTAMPTZ,
    lifted_by     VARCHAR(255)
);

-- The gate ("is this user banned right now?") reads by user with lifted_at
-- NULL; keep that cheap. A partial unique index also makes a second ACTIVE ban
-- for the same user a no-op (ON CONFLICT DO NOTHING) while still allowing a
-- fresh ban after a previous one was lifted.
CREATE UNIQUE INDEX IF NOT EXISTS uq_service_bans_active
    ON service_bans (user_id) WHERE lifted_at IS NULL;

COMMENT ON TABLE service_bans IS
    'LOCAL-728/D691/D658: a user banned from the service by the administrator — '
    'no purchases, generation, community joins or creation. Downloaded audio '
    'stays on the device (D658: a ban blocks NEW access only). lifted_at IS '
    'NULL = active; a lifted ban keeps its row as history (never deleted).';

-- ─── 3. admin_actions — the audit ledger (append-only) ──────────────────────
CREATE TABLE IF NOT EXISTS admin_actions (
    id            SERIAL PRIMARY KEY,
    -- 'bar' | 'unbar' | 'ban' | 'unban' | 'disable_community' |
    -- 'enable_community'. A free-ish text (CHECK keeps it to the known verbs)
    -- so a new verb is one additive migration away.
    action        VARCHAR(32) NOT NULL
                  CHECK (action IN ('bar', 'unbar', 'ban', 'unban',
                                    'disable_community', 'enable_community')),
    -- WHO performed it (the admin operator label, e.g. 'moderation.py' or an
    -- operator id). Free text: the admin surface is trusted.
    actor         VARCHAR(255),
    -- The target user (bar/unbar/ban/unban) and/or community (bar/unbar/
    -- disable/enable). Both nullable — a service ban has no community, a
    -- community disable has no user.
    target_user_id   VARCHAR(255),
    target_community_id INTEGER,
    reason        TEXT,
    -- The report this action answers, when any (tour_reports.id or
    -- community_reports.id — the ledger does not FK either, to stay additive
    -- and survive a report cascade; the id is recorded for the paper trail).
    report_id     INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reading the ledger newest-first (the CLI `log` view) is the common query.
CREATE INDEX IF NOT EXISTS idx_admin_actions_created
    ON admin_actions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_actions_target_user
    ON admin_actions (target_user_id);

COMMENT ON TABLE admin_actions IS
    'LOCAL-728/D691: append-only audit ledger of every administrator moderation '
    'action (bar/unbar a member from a community, ban/unban from the service, '
    'disable/enable a community). Records who, when, target, reason and the '
    'answered report id. Never updated or deleted.';

COMMIT;
