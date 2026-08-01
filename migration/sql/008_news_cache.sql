-- Migration 008: News Cache table for article audio caching
-- Part of LOCAL-73 (news articles have no cache)
--
-- Caches a reference (article_id) to the already-stored audio in news_audios.
-- Does NOT duplicate the ZIP blob — just maps content-hash → article_id.
--
-- Cache key = SHA256(normalized_article_text + "|" + major_points_count)
-- TTL enforced at read time (configurable via NEWS_CACHE_TTL_HOURS env var).
-- Expired entries are cleaned up opportunistically.

BEGIN;

CREATE TABLE IF NOT EXISTS news_cache (
    cache_key VARCHAR(64) PRIMARY KEY,
    article_id VARCHAR(255) NOT NULL,
    article_text_hash VARCHAR(64) NOT NULL,
    major_points_count INTEGER NOT NULL DEFAULT 0,
    request_string TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hit_count INTEGER DEFAULT 0,
    content_length INTEGER DEFAULT 0
);

-- For TTL expiration scans
CREATE INDEX IF NOT EXISTS idx_news_cache_created_at
ON news_cache (created_at);

-- For lookup by article_id (reverse lookup: "is this article cached?")
CREATE INDEX IF NOT EXISTS idx_news_cache_article_id
ON news_cache (article_id);

COMMENT ON TABLE news_cache IS 'Content-addressed cache for news audio. Maps article text hash to existing news_audios row.';
COMMENT ON COLUMN news_cache.cache_key IS 'SHA256 of normalized_text + "|" + major_points_count';
COMMENT ON COLUMN news_cache.article_id IS 'FK to article_requests.article_id / news_audios.article_id';
COMMENT ON COLUMN news_cache.article_text_hash IS 'SHA256 of raw article_text (for audit/debugging)';
COMMENT ON COLUMN news_cache.created_at IS 'When the cache entry was created/refreshed. Used for TTL.';
COMMENT ON COLUMN news_cache.hit_count IS 'Number of cache hits (incremented atomically on each hit)';

COMMIT;
