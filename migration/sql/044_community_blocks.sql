-- 044_community_blocks.sql  (LOCAL-726, lawyer review item 10 — Apple Guideline 1.2)
--
-- A block function for communities. Apple's user-generated-content rules
-- (Guideline 1.2) require the ability to BLOCK abusive users; the lawyer's
-- review (ClickUp wdvrdayzt2 item 10) flagged that Audioura had none. This adds
-- it, PURELY ADDITIVELY and idempotently, in ONE table. NO DROP, NO DELETE, NO
-- column retype. Applying twice is a no-op (CREATE TABLE / INDEX IF NOT EXISTS).
--
-- ONE table, community_blocks, carries BOTH directions of block the feature
-- needs, distinguished by `kind`:
--
--   kind = 'member_block'  — a MEMBER blocks an organiser or another member.
--       The blocker (blocker_user_id) no longer wants to see the blocked user's
--       communities or community tours. This is the blocker's OWN view: a
--       blocked organiser's communities and community tours disappear FOR THE
--       BLOCKER only. It does not remove anyone from anything. community_id is
--       the community the block was made from (context); the hide is applied
--       wherever blocked_user_id owns/authored content the blocker would see.
--
--   kind = 'organiser_bar' — an ORGANISER bars (removes and bars) a MEMBER from
--       THEIR community. blocker_user_id is the organiser (the community owner),
--       blocked_user_id the barred member, community_id the community. A barred
--       member loses access to NEW content (D658: downloaded audio stays on the
--       device — the server never deletes it) and CANNOT REJOIN BY CODE: the
--       pass-purchase and join paths refuse a barred user for that community.
--
-- The caller (communities_api.py) owns the rules; this is just the store.
--
--   community_id      the community the block is scoped to. FK to communities;
--                     ON DELETE CASCADE — deleting a community removes its
--                     blocks (they are meaningless without it).
--   blocker_user_id   who blocked. For organiser_bar this is the owner; for a
--                     member_block it is the blocking member. Device secret_id,
--                     the same identity space as community_memberships.user_id.
--   blocked_user_id   who is blocked/barred.
--   kind              'member_block' | 'organiser_bar' (CHECK-constrained).
--   reason            optional free text (why — for the organiser's own record).
--   created_at        when the block was made.
--
-- One block per (community, blocker, blocked, kind): blocking twice is a no-op
-- (the API upserts ON CONFLICT DO NOTHING). Unblock is a DELETE of the one row
-- (done by the blocker — a member unblocks from Settings, an organiser lifts a
-- bar from the member list), which is why the table is safe to delete FROM: it
-- holds only block rows, never membership or content.

BEGIN;

CREATE TABLE IF NOT EXISTS community_blocks (
    id               SERIAL PRIMARY KEY,
    community_id     INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    blocker_user_id  VARCHAR(255) NOT NULL,
    blocked_user_id  VARCHAR(255) NOT NULL,
    kind             VARCHAR(16) NOT NULL
                     CHECK (kind IN ('member_block', 'organiser_bar')),
    reason           TEXT,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- You cannot block yourself (a no-op that would only confuse the queries).
    CONSTRAINT chk_community_blocks_not_self
        CHECK (blocker_user_id <> blocked_user_id),
    -- One block per (community, blocker, blocked, kind). Re-blocking is a no-op.
    CONSTRAINT uq_community_blocks
        UNIQUE (community_id, blocker_user_id, blocked_user_id, kind)
);

-- "Is THIS user barred from THIS community?" (the join/purchase gate) and
-- "who has this organiser barred?" (the member list) read by (community,
-- blocked, kind); keep that cheap.
CREATE INDEX IF NOT EXISTS idx_community_blocks_blocked
    ON community_blocks (community_id, blocked_user_id, kind);

-- "What has THIS member blocked?" (Settings unblock list; the hide filter on
-- the member's own views) reads by blocker.
CREATE INDEX IF NOT EXISTS idx_community_blocks_blocker
    ON community_blocks (blocker_user_id, kind);

COMMENT ON TABLE community_blocks IS
    'LOCAL-726 / Apple Guideline 1.2: community block function. '
    'kind=member_block: a member hides a blocked user''s communities/tours from '
    'their OWN view. kind=organiser_bar: an organiser removes and bars a member '
    'from their community (no new content, cannot rejoin by code; downloaded '
    'audio stays, D658). Unblock = DELETE the row (member from Settings, '
    'organiser from the member list).';

COMMIT;
