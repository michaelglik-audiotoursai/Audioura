-- 050_community_episode_metadata.sql  (LOCAL-759 C)
--
-- The organiser-audio builder's import checklist shows each feed episode's SIZE
-- and duration, and a running total of the ticked episodes ("3 episodes · 285
-- MB"), so the organiser knows how big a download they are about to publish to
-- their members (Michael's Salem tour was 285 MB across three podcast episodes).
--
-- For that the feed's own metadata must survive the import: three NULLABLE
-- columns on community_episodes. Purely ADDITIVE and idempotent — three
-- ADD COLUMN IF NOT EXISTS, no DROP, no DELETE, no retype, no NOT NULL (every
-- existing row reads back NULL, which the app's metaLine simply omits). Applying
-- it twice is a no-op; row counts before/after are identical.

BEGIN;

-- Enclosure byte length (the number summed into the checklist total). NULL when
-- the feed omits <enclosure length="…"> or the episode was a hand-typed link.
ALTER TABLE community_episodes
    ADD COLUMN IF NOT EXISTS size_bytes BIGINT;

-- The episode duration as the feed gave it ('48:12' or '3600'). Raw text — the
-- app formats it; the server never converts. NULL when the feed omits it.
ALTER TABLE community_episodes
    ADD COLUMN IF NOT EXISTS duration VARCHAR(32);

-- The publish date as the feed gave it (<pubDate>). Raw text so no timezone/
-- format assumption is baked in. NULL when the feed omits it.
ALTER TABLE community_episodes
    ADD COLUMN IF NOT EXISTS episode_date VARCHAR(64);

COMMENT ON COLUMN community_episodes.size_bytes IS
    'LOCAL-759 C: enclosure byte length from the feed (NULL when absent). The '
    'organiser-audio builder sums ticked episodes into "N episodes · X MB".';
COMMENT ON COLUMN community_episodes.duration IS
    'LOCAL-759 C: episode duration as the feed gave it (raw text, NULL absent).';
COMMENT ON COLUMN community_episodes.episode_date IS
    'LOCAL-759 C: episode publish date as the feed gave it (raw text, NULL absent).';

COMMIT;
