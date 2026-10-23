-- 048_community_release_cadence.sql  (LOCAL-738, Michael's review 2026-10-22 C2c)
--
-- "How often will members get new tours?" — a new REQUIRED choice on the create
-- form (day | week | month | year, default 'week'). Stored on the community so
-- the community page can show "New tours: weekly". Purely ADDITIVE and
-- idempotent: ONE ADD COLUMN IF NOT EXISTS with a DEFAULT, plus ONE guarded
-- CHECK that only constrains the new column. NO DROP of a column, NO DELETE of
-- a row, NO column retype. Applying it twice is a no-op. Row counts before/
-- after are identical for every existing table — it adds a column only, never
-- a data row.
--
-- The DEFAULT 'week' means every existing community (created before this
-- column) reads back release_cadence = 'week' — the same default the form
-- offers — so the community page has a sensible value for old rows without a
-- backfill pass.

BEGIN;

-- ─── The release cadence column (default 'week') ─────────────────────────────
ALTER TABLE communities
    ADD COLUMN IF NOT EXISTS release_cadence VARCHAR(10) NOT NULL DEFAULT 'week';

-- ─── Constrain it to the four lengths (guarded, idempotent) ──────────────────
-- Only ever asserts the one fixed domain; a re-run drops and re-adds the same
-- shape, touching no row (every existing value is 'week' by default, which is
-- in the set).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_communities_release_cadence'
          AND conrelid = 'communities'::regclass
    ) THEN
        ALTER TABLE communities DROP CONSTRAINT chk_communities_release_cadence;
    END IF;
    ALTER TABLE communities
        ADD CONSTRAINT chk_communities_release_cadence
        CHECK (release_cadence IN ('day', 'week', 'month', 'year'));
END $$;

COMMENT ON COLUMN communities.release_cadence IS
    'LOCAL-738 (C2c): how often members get new tours — day | week | month | '
    'year. Chosen on the create form (required, default week), returned by the '
    'community page payload and shown as "New tours: weekly".';

COMMIT;
