-- 045_community_reports_triage.sql  (LOCAL-728, D691)
--
-- Michael's ruling (D691): members and organisers do NOT block each other —
-- they REPORT to Audioura, and only the administrator bars or bans. The app's
-- single "Report to Audioura" form (community page ⋯) writes a row here; the
-- admin reviews it with moderation.py.
--
-- community_reports ALREADY exists (migration 029) with:
--     id, community_id, reporter_user_id, reason, created_at
-- Migration 029 described it as "a report routes to the OWNER". Under D691 a
-- community report goes to AUDIOURA, exactly like a tour report (tour_reports,
-- migration 042). This migration brings community_reports up to the same
-- triage shape as tour_reports, PURELY ADDITIVELY and idempotently:
--
--   * add `detail`  — the optional free text the reporter typed, kept separate
--                     from `reason` (which now carries the chosen reason code,
--                     e.g. 'spam', 'offensive', 'other'). Both are nullable, so
--                     every existing row stays valid.
--   * add `status`  — 'open' (default) | 'reviewed' | 'dismissed', the same
--                     triage lifecycle tour_reports uses. Existing rows backfill
--                     to 'open' via the column DEFAULT.
--
-- NO DROP, NO DELETE, NO column retype, no change to the existing columns or
-- the FK. Applying twice is a no-op (ADD COLUMN IF NOT EXISTS; the CHECK is
-- added only when absent). Row counts before/after are identical — this adds
-- columns, never rows.

BEGIN;

ALTER TABLE community_reports
    ADD COLUMN IF NOT EXISTS detail TEXT;

ALTER TABLE community_reports
    ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'open';

-- The triage status is constrained to the same three values as tour_reports.
-- Added separately (not inline) and guarded so a re-run does not error on an
-- already-present constraint.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_community_reports_status'
    ) THEN
        ALTER TABLE community_reports
            ADD CONSTRAINT chk_community_reports_status
            CHECK (status IN ('open', 'reviewed', 'dismissed'));
    END IF;
END$$;

-- Triage reads the open reports newest-first; keep that cheap (mirrors the
-- tour_reports index).
CREATE INDEX IF NOT EXISTS idx_community_reports_status_created
    ON community_reports (status, created_at DESC);

COMMENT ON TABLE community_reports IS
    'LOCAL-728/D691: a report on a community, organiser or community tour goes '
    'to AUDIOURA (not the owner). reason = the chosen reason code, detail = the '
    'reporter''s optional free text, status = open|reviewed|dismissed (triaged '
    'with moderation.py). Supersedes the 029 "routes to the OWNER" note.';

COMMIT;
