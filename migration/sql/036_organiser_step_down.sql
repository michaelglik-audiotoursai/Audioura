-- 036_organiser_step_down.sql  (LOCAL-702, D663 §1)
--
-- Organiser steps down — hand-over, closed to new members, archive after 30
-- days. Purely ADDITIVE and idempotent, wrapped in one transaction. Applying
-- twice is a no-op (ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS /
-- value-asserting UPDATE). NO DROP, NO DELETE, NO column retype.
--
-- THE STATE MACHINE (D663 §1). A community moves through:
--
--   active   → the normal state. New members may join and buy passes.
--   handover → the owner tapped "Step down as organiser" (D663 §1 (a)). The
--              community STAYS readable/playable for existing members, but it
--              REFUSES new joins and pass sales (409 community_closed_to_new_
--              members) and shows "Looking for a new organiser" to members.
--              A member can volunteer; the stepping-down owner picks one; the
--              member accepts → becomes owner, new terms accepted (LOCAL-691
--              document_acceptance), the community REOPENS (→ active).
--   archived → no new organiser within 30 days of stepping down (D663 §1 (c)).
--              A daily job on the tick flips handover→archived at day 30.
--              Archived members keep their downloads; nothing new is served or
--              sold. Terminal (a hand-over can no longer complete).
--
-- WHAT THIS ADDS:
--   1. communities.status            — 'active' | 'handover' | 'archived'
--                                       (DEFAULT 'active'; every existing row
--                                       is 'active', so behaviour is unchanged
--                                       until an owner steps down).
--   2. communities.stepped_down_at   — when the owner stepped down. The 30-day
--                                       archive clock is measured from here.
--   3. communities.archived_at       — when the daily job archived it (NULL
--                                       until then).
--   4. community_organiser_offers    — the hand-over offers: one row per member
--                                       who volunteers, the owner's pick, and
--                                       the acceptance that transfers ownership.

BEGIN;

-- ─── 1-3. community status + hand-over timestamps ────────────────────────────
ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'active';

-- The archive clock origin — set when the owner steps down, cleared when a new
-- organiser accepts (the community reopens with a fresh slate).
ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS stepped_down_at TIMESTAMP;

ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP;

-- The status domain. Added separately + guarded so a re-run does not duplicate
-- the constraint (ADD CONSTRAINT has no IF NOT EXISTS).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_communities_status'
          AND conrelid = 'communities'::regclass
    ) THEN
        ALTER TABLE communities
            ADD CONSTRAINT chk_communities_status
            CHECK (status IN ('active', 'handover', 'archived'));
    END IF;
END $$;

-- Every pre-existing community is active (the DEFAULT covers new rows; this
-- value-asserting UPDATE covers any row that somehow has a NULL/blank status,
-- and is a harmless no-op on a fresh DB).
UPDATE communities SET status = 'active'
    WHERE status IS NULL OR status = '';

-- The archive job scans handover communities by their step-down date; a partial
-- index keeps that scan cheap and touches only the (small) handover set.
CREATE INDEX IF NOT EXISTS idx_communities_handover
    ON communities (stepped_down_at)
    WHERE status = 'handover';

COMMENT ON COLUMN communities.status IS
    'LOCAL-702/D663 §1: active (normal), handover (owner stepped down — closed '
    'to new members, looking for a new organiser), or archived (no new organiser '
    'within 30 days; members keep downloads, nothing new).';
COMMENT ON COLUMN communities.stepped_down_at IS
    'LOCAL-702/D663 §1: when the owner stepped down. The 30-day archive clock is '
    'measured from here; cleared when a new organiser accepts (community reopens).';
COMMENT ON COLUMN communities.archived_at IS
    'LOCAL-702/D663 §1: when the daily job archived the community (NULL until then).';


-- ─── 4. community_organiser_offers — the hand-over offers ────────────────────
-- One row per member who VOLUNTEERS to take over a community that is in
-- handover. The stepping-down owner PICKS one (picked_at); the picked member
-- ACCEPTS (accepted_at) → ownership transfers and the community reopens. A
-- member may volunteer once per community (unique). The lifecycle is captured
-- by the three timestamps + status so a test can assert every transition:
--
--   offered  → the member volunteered (created_at set, picked_at/accepted_at NULL).
--   picked   → the owner picked this volunteer (picked_at set). At most one
--              offer per community can be 'picked' at a time (the owner picks
--              one; picking another supersedes the first — see the API).
--   accepted → the picked member accepted (accepted_at set) → they are now the
--              owner. Terminal.
--   withdrawn→ the member withdrew their offer, or it was superseded when the
--              owner picked someone else. Inert.
CREATE TABLE IF NOT EXISTS community_organiser_offers (
    id            SERIAL PRIMARY KEY,
    community_id  INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    -- The volunteering member's device secret_id (same identity space as
    -- community_memberships.user_id).
    member_user_id VARCHAR(255) NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'offered'
                  CHECK (status IN ('offered', 'picked', 'accepted', 'withdrawn')),
    picked_at     TIMESTAMP,
    accepted_at   TIMESTAMP,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- A member volunteers at most once per community (re-volunteering reuses the
    -- row — see the API's ON CONFLICT).
    CONSTRAINT uq_organiser_offers UNIQUE (community_id, member_user_id)
);
CREATE INDEX IF NOT EXISTS idx_organiser_offers_community
    ON community_organiser_offers (community_id);
-- At most one PICKED offer per community (the owner picks exactly one). A
-- partial unique index enforces it; picking another supersedes the first in the
-- API before this would ever fire.
CREATE UNIQUE INDEX IF NOT EXISTS uq_organiser_offers_one_picked
    ON community_organiser_offers (community_id)
    WHERE status = 'picked';

COMMENT ON TABLE community_organiser_offers IS
    'LOCAL-702/D663 §1: hand-over offers. A member volunteers (offered); the '
    'stepping-down owner picks one (picked); the picked member accepts (accepted) '
    '→ ownership transfers and the community reopens. One offer per (community, '
    'member); at most one picked offer per community.';

COMMIT;
