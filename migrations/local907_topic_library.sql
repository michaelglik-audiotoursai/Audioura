-- LOCAL-907 (D772): Regional Topic Library ("fillings" between stops).
-- ADDITIVE migration only: three NEW tables, nothing existing is altered or dropped.
-- Run (by LEAD, after merge):  psql -f migrations/local907_topic_library.sql
-- It is idempotent (IF NOT EXISTS) and contains no DELETE / DROP / ALTER of existing objects.

-- One reusable spoken segment per region / theme / language.
CREATE TABLE IF NOT EXISTS topic_segments (
    id                 BIGSERIAL PRIMARY KEY,
    region_key         TEXT        NOT NULL,
    theme              TEXT        NOT NULL,
    title              TEXT        NOT NULL,
    language           TEXT        NOT NULL DEFAULT 'en',
    text               TEXT        NOT NULL,
    word_count         INTEGER     NOT NULL DEFAULT 0,
    est_minutes        NUMERIC(6,2) NOT NULL DEFAULT 0,      -- word_count / 150 wpm
    sources            JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- [{url,title,revision_id,licence,...}]
    credit_line        TEXT        NOT NULL DEFAULT '',
    centroid_lat       DOUBLE PRECISION,
    centroid_lng       DOUBLE PRECISION,
    radius_km          DOUBLE PRECISION,
    audio_path         TEXT,                                  -- nullable until rendered
    source_segment_id  BIGINT REFERENCES topic_segments(id),  -- set on translations
    status             TEXT        NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft', 'ready', 'rejected')),
    cost_usd           NUMERIC(10,6) NOT NULL DEFAULT 0,
    created_at         TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_topic_segments_region
    ON topic_segments (region_key, language, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_topic_segments_region_lang_title
    ON topic_segments (region_key, language, title);

-- What a listener did with a segment (drives theme preferences and no-repeat).
CREATE TABLE IF NOT EXISTS listening_events (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    tour_id     TEXT        NOT NULL,
    segment_id  BIGINT      NOT NULL REFERENCES topic_segments(id),
    action      TEXT        NOT NULL CHECK (action IN ('start', 'skip', 'finish', 'choose')),
    at_sec      DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_listening_events_user
    ON listening_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listening_events_user_tour
    ON listening_events (user_id, tour_id);

-- Learned preference per listener per theme, clamped to [-5, 5].
CREATE TABLE IF NOT EXISTS listener_theme_weights (
    user_id     TEXT        NOT NULL,
    theme       TEXT        NOT NULL,
    weight      DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, theme)
);
