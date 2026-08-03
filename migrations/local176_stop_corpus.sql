-- LOCAL-176: Per-stop corpus attribution table
-- Additive migration only: new table, no changes to existing schema.
-- Run: psql -f migrations/local176_stop_corpus.sql
--
-- This table stores page passages attributed to individual stops/works,
-- enabling per-stop anchor detection that the venue-level corpus cannot support.

CREATE TABLE IF NOT EXISTS stop_corpus (
    id SERIAL PRIMARY KEY,
    venue_name TEXT NOT NULL,
    stop_title TEXT NOT NULL,
    passages_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_pages JSONB NOT NULL DEFAULT '[]'::jsonb,
    passage_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(venue_name, stop_title)
);

-- Index for efficient lookup by venue
CREATE INDEX IF NOT EXISTS idx_stop_corpus_venue ON stop_corpus(venue_name);

-- Index for lookup by stop title  
CREATE INDEX IF NOT EXISTS idx_stop_corpus_stop ON stop_corpus(stop_title);
