-- 031_tour_unlock_consumption.sql  (LOCAL-693, D660)
--
-- "Every download of a paid tour is paid; what is on the phone is the listener's
--  forever." (Michael, 2026-10-14) — this OVERRULES the earlier buy-once /
--  free-re-download model (LOCAL-677B). From now on a tour_unlocks row grants
--  exactly ONE successful download to ONE phone. Deleting the tour, moving to a
--  new phone, or reinstalling means buying again; each language is still its own
--  purchase (D653 unchanged); listening on the phone stays unlimited and offline
--  (D654 unchanged).
--
-- WHAT THIS ADDS, PURELY ADDITIVELY:
--
--   1. tour_unlocks.consumed_at TIMESTAMPTZ NULL — when the purchase was spent by
--      a successful download. NULL = UNCONSUMED (an active entitlement to one
--      download). Every existing row stays NULL, so already-bought tours remain
--      downloadable once under D660 (a fair, non-breaking default: a listener who
--      bought before D660 and has not yet downloaded still gets their download;
--      one who already downloaded under the old free-re-download rule simply has
--      an unconsumed row they can spend once — acceptable and generous).
--
--   2. tour_unlocks.consumed_by_download_id VARCHAR(255) NULL — the download
--      event id (the app's download token / the map-delivery download id) that
--      consumed this unlock. Audit only; lets a consumed row be traced to the
--      download that spent it. NULL while unconsumed.
--
--   3. The idempotency key changes from a FULL UNIQUE(user_id, tour_id) to a
--      PARTIAL unique index on (user_id, tour_id) WHERE consumed_at IS NULL.
--      Why: D660 requires a user to be able to BUY the same language row AGAIN
--      after consuming the previous purchase — the old full-table UNIQUE made the
--      second purchase a silent no-op (ON CONFLICT DO NOTHING), which under D660
--      would swallow the new purchase and leave the buyer with no download. The
--      partial index keeps the SAME guarantee where it still matters — a buyer
--      can hold at most ONE active (unconsumed) unlock per (user, language row),
--      so a replayed/duplicate purchase of an unspent unlock is still a no-op —
--      while allowing a fresh unlock once the previous one is consumed. Store
--      idempotency is unchanged and still primary: purchases.transaction_id is
--      UNIQUE, so a replayed transaction is caught there (409 already_verified)
--      before any unlock insert runs.
--
-- Idempotent & safe to re-run: ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT
-- EXISTS, and a guarded DROP of the old named constraint (only if present). No
-- DROP of a column, no DELETE of a row, no change to an existing column's type.
-- The service's self-healing DDL in map_delivery/app.py and entitlements_api.py
-- converges to the same shape whether or not this file was ever run.

BEGIN;

-- ─── 1. consumed_at + consumed_by_download_id on tour_unlocks ────────────────
ALTER TABLE tour_unlocks
    ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ;

ALTER TABLE tour_unlocks
    ADD COLUMN IF NOT EXISTS consumed_by_download_id VARCHAR(255);

COMMENT ON COLUMN tour_unlocks.consumed_at IS
    'LOCAL-693/D660: when this purchase was spent by a SUCCESSFUL download. '
    'NULL = unconsumed (an active entitlement to exactly one download). A failed '
    'or cut-off download never sets this; the listener retries for free until a '
    'download completes.';
COMMENT ON COLUMN tour_unlocks.consumed_by_download_id IS
    'LOCAL-693/D660: the download event id that consumed this unlock (audit). '
    'NULL while unconsumed.';

-- ─── 2. Replace the full UNIQUE(user_id,tour_id) with a PARTIAL unique index ──
-- Drop the old table-wide uniqueness so a user can buy the same language row
-- again after consuming the prior unlock. Guarded: only if the named constraint
-- still exists (idempotent re-run, and tolerant of a DB whose constraint carries
-- a different auto-generated name).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_tour_unlocks_user_tour'
          AND conrelid = 'tour_unlocks'::regclass
    ) THEN
        ALTER TABLE tour_unlocks DROP CONSTRAINT uq_tour_unlocks_user_tour;
    END IF;
END $$;

-- At most ONE active (unconsumed) unlock per (user, language row). A consumed
-- row no longer blocks a fresh purchase, so re-buying after a download works;
-- a replayed purchase of an unspent unlock still conflicts (no-op), preserving
-- unlock idempotency exactly where D660 still wants it.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tour_unlocks_active
    ON tour_unlocks (user_id, tour_id)
    WHERE consumed_at IS NULL;

-- Keep the fast "has this user unlocked this tour?" lookups the gate and the
-- verified-rating check already use (idx_tour_unlocks_user_tour from 022 stays).
-- A partial index to find the oldest unconsumed unlock to consume on download.
CREATE INDEX IF NOT EXISTS idx_tour_unlocks_unconsumed
    ON tour_unlocks (user_id, tour_id, created_at)
    WHERE consumed_at IS NULL;

COMMIT;
