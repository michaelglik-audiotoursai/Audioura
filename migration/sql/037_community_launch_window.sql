-- 037_community_launch_window.sql  (LOCAL-703, D664)
--
-- A new community must win its first TWO members within a week, or it is
-- archived and its invite code stops working. The organiser sees a live
-- countdown. Purely ADDITIVE and idempotent, wrapped in one transaction.
-- Applying twice is a no-op (ADD COLUMN IF NOT EXISTS / value-asserting
-- backfill). NO DROP, NO DELETE, NO column retype.
--
-- THE RULE (D664, LEAD's recorded reading):
--
--   * The window is COMMUNITY_LAUNCH_HOURS = 168 h (7 days) from creation,
--     configurable in the server. launch_deadline = created_at + the window.
--   * A community is LAUNCHED when it has >= 2 QUALIFYING members, EXCLUDING the
--     owner. Paid communities: members holding a verified paid pass. Free
--     communities: joined members. Launch is checked on every join / pass
--     verification; launched_at is stamped ONCE and never reverted.
--   * Miss the bar (past the deadline, still not launched) → the launch-window
--     job sets status 'archived' (the LOCAL-702 terminal state), archived_at,
--     and archived_reason = 'launch_window_missed'. The invite code then
--     resolves to 410 community_closed ("This community has closed"). Members
--     keep their downloads (D658). Meet the bar → launched, the countdown is
--     gone for good; a launched community is never archived by this job.
--   * The organiser is reminded at 48 h and 12 h left (once each) — the
--     launch-window job stamps the reminder columns so it never double-sends.
--   * Communities created BEFORE this rule (the two demo communities) get the
--     FULL window from the moment the rule ships: the backfill below sets their
--     launch_deadline = NOW() + the window.
--
-- WHAT THIS ADDS:
--   1. communities.launch_deadline        — created_at + window; when the first
--                                            two qualifying members are due.
--   2. communities.launched_at            — stamped once the bar is met; NULL
--                                            until then. Never reverted.
--   3. communities.archived_reason        — why the community was archived:
--                                            'launch_window_missed' (this task)
--                                            or 'handover_expired' (LOCAL-702's
--                                            30-day path, backfilled below for
--                                            rows already archived that way).
--   4. communities.launch_reminded_48h_at — when the 48 h-left reminder was
--                                            sent (NULL until then).
--   5. communities.launch_reminded_12h_at — when the 12 h-left reminder was
--                                            sent (NULL until then).

BEGIN;

-- ─── 1-5. launch-window columns ──────────────────────────────────────────────
ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS launch_deadline TIMESTAMPTZ;

ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS launched_at TIMESTAMPTZ;

ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS archived_reason VARCHAR(32);

ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS launch_reminded_48h_at TIMESTAMPTZ;

ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS launch_reminded_12h_at TIMESTAMPTZ;

-- The archived_reason domain. Added separately + guarded so a re-run does not
-- duplicate the constraint (ADD CONSTRAINT has no IF NOT EXISTS). NULL is
-- allowed (a non-archived community has no reason).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_communities_archived_reason'
          AND conrelid = 'communities'::regclass
    ) THEN
        ALTER TABLE communities
            ADD CONSTRAINT chk_communities_archived_reason
            CHECK (archived_reason IS NULL
                   OR archived_reason IN ('launch_window_missed', 'handover_expired'));
    END IF;
END $$;

-- Backfill the deadline for every community that has none yet. Communities
-- created before this rule (the two demo communities) get the FULL window from
-- the moment the rule ships: deadline = NOW() + COMMUNITY_LAUNCH_HOURS (168 h).
-- A community already launched (if any) also gets a deadline for shape, but the
-- job never archives a launched community. Idempotent: a re-run only touches
-- rows still NULL.
UPDATE communities
    SET launch_deadline = NOW() + INTERVAL '168 hours'
    WHERE launch_deadline IS NULL;

-- Any community already archived via the LOCAL-702 30-day hand-over path gets
-- its reason recorded, so archived_reason is meaningful for every archived row
-- (not just the ones this task archives). A fresh DB has none; this is a
-- harmless no-op there.
UPDATE communities
    SET archived_reason = 'handover_expired'
    WHERE status = 'archived' AND archived_reason IS NULL;

-- The launch-window job scans active, un-launched communities by their
-- deadline; a partial index keeps that scan cheap (it only has to look at the
-- communities still in their window).
CREATE INDEX IF NOT EXISTS idx_communities_launch_window
    ON communities (launch_deadline)
    WHERE status = 'active' AND launched_at IS NULL;

COMMENT ON COLUMN communities.launch_deadline IS
    'LOCAL-703/D664: created_at + COMMUNITY_LAUNCH_HOURS (168 h). By this time '
    'the community needs 2 qualifying members (excluding the owner) or the '
    'launch-window job archives it. Pre-rule communities got NOW()+window at '
    'migration.';
COMMENT ON COLUMN communities.launched_at IS
    'LOCAL-703/D664: when the community won its first 2 qualifying members '
    '(excluding the owner). Stamped once, never reverted. NULL = not yet '
    'launched; a launched community is never archived by the launch-window job.';
COMMENT ON COLUMN communities.archived_reason IS
    'LOCAL-703/D664: why a community was archived — launch_window_missed '
    '(missed the first-two-members bar) or handover_expired (LOCAL-702 30-day '
    'hand-over path). NULL when not archived.';
COMMENT ON COLUMN communities.launch_reminded_48h_at IS
    'LOCAL-703/D664: when the organiser 48 h-left launch reminder was sent '
    '(NULL until then). Guards against double-sending.';
COMMENT ON COLUMN communities.launch_reminded_12h_at IS
    'LOCAL-703/D664: when the organiser 12 h-left launch reminder was sent '
    '(NULL until then). Guards against double-sending.';

COMMIT;
