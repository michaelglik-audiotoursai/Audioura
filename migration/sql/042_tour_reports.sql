-- 042: a row per in-app content report (LOCAL-724 item 5).
-- Additive, idempotent. "Report This Tour" in the app opened a mailto: to
-- info@audioura.com (my_tours_screen.dart) — the approved Content Policy
-- described that honestly as "it opens an email". This table lets the app POST a
-- report to the server instead, so each report is ONE row in a reviewable queue
-- rather than a message in an inbox, and the policy text can say "in-app".
--
--   tour_id       the reported tour (audio_tours.id). Kept even if the tour is
--                 later hidden/removed — ON DELETE SET NULL so a report is never
--                 silently lost with its tour, and NO report ever deletes a tour.
--   tour_name     snapshot of the tour's name at report time (the tour may be
--                 renamed or re-generated later; the report still reads clearly).
--   reason        optional free text the reporter typed.
--   reporter_user_id  optional: who reported (app user id), when the app sends it.
--   status        'open' (default) | 'reviewed' | 'dismissed'. A human triages;
--                 NOTHING here lists/hides a tour on its own (D656 add. 2:
--                 approve/reject stays with Michael, via review_queue.py).
--   created_at    when the report arrived.
CREATE TABLE IF NOT EXISTS tour_reports (
    id            SERIAL PRIMARY KEY,
    tour_id       INTEGER REFERENCES audio_tours(id) ON DELETE SET NULL,
    tour_name     TEXT,
    reason        TEXT,
    reporter_user_id TEXT,
    status        VARCHAR(16) NOT NULL DEFAULT 'open'
                  CHECK (status IN ('open', 'reviewed', 'dismissed')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Triage reads the open reports newest-first; keep that cheap.
CREATE INDEX IF NOT EXISTS idx_tour_reports_status_created
    ON tour_reports (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tour_reports_tour_id
    ON tour_reports (tour_id);
