-- LOCAL-907E: per-sentence end times (seconds) of a rendered topic segment, for the phone's
-- sentence highlight. ADDITIVE only: one nullable column; nothing dropped, deleted or rewritten.
-- Run (by LEAD, after merge, BEFORE deploying the code that SELECTs it):
--   psql -f migrations/local907e_topic_sentence_ends.sql
ALTER TABLE topic_segments ADD COLUMN IF NOT EXISTS sentence_ends JSONB;
