-- 032_tour_unlock_restore.sql  (LOCAL-693B, D660 — LEAD review of 693)
--
-- LEAD review: consumption must be decided by the SERVER, not the app. In 693 a
-- purchase was consumed only when the app called POST /tour/<id>/download-
-- complete; a modified app (or a direct API call — the gateway key ships inside
-- the app) could simply never call it and download forever. 693B moves the
-- decision server-side: map-delivery stamps consumed_at when the streaming
-- generator yields the LAST byte of the zip (a cut-off stream never reaches that
-- point, so a failed download still never consumes — D660). The app no longer
-- confirms success; instead it reports FAILURE via POST /tour/<id>/download-
-- failed when it received the bytes but could not save/validate the zip. The
-- server then RESTORES that purchase exactly ONCE, only within 24h of
-- consumption.
--
-- WHAT THIS ADDS, PURELY ADDITIVELY:
--
--   1. tour_unlocks.restored_at TIMESTAMPTZ NULL — when a consumed unlock was
--      restored (un-consumed) by a download-failed report. NULL = never
--      restored. A row that already carries restored_at cannot be restored a
--      second time (the restore endpoint returns 409): one restore per
--      purchase, so a modified app cannot loop failed-download to download
--      forever.
--
-- RESTORE SEMANTICS (enforced in map_delivery/app.py, not in SQL):
--   * A download-failed call finds the MOST-RECENTLY consumed unlock for
--     (user, language row) whose consumed_at is within the last 24h and whose
--     restored_at IS NULL. It clears consumed_at / consumed_by_download_id and
--     stamps restored_at = NOW(). The listener may then download once more free.
--   * Second failed-report for the same purchase (restored_at already set) → the
--     app gets 409. Beyond 24h of consumption → 409. No eligible row → 409.
--
-- Idempotent & safe to re-run: ADD COLUMN IF NOT EXISTS only. No DROP, no
-- DELETE, no type change. The service self-heals to the same shape via
-- _ensure_unlock_consumption_columns() whether or not this file was run.

BEGIN;

ALTER TABLE tour_unlocks
    ADD COLUMN IF NOT EXISTS restored_at TIMESTAMPTZ;

COMMENT ON COLUMN tour_unlocks.restored_at IS
    'LOCAL-693B/D660: when a consumed unlock was restored once by a download-'
    'failed report (within 24h of consumption). NULL = never restored. A row '
    'with restored_at set cannot be restored again (download-failed → 409), so a '
    'failed-download loop cannot grant unlimited downloads.';

COMMIT;
