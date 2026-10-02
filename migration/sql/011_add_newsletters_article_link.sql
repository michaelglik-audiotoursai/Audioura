-- ============================================================================
-- Migration 011: Add newsletters_article_link to audiotours_subscribed
-- LOCAL-225: Discovered via dry-run — entitlements.py queries this table
--            but LOCAL-211 did not include it.
-- ============================================================================
-- PURPOSE:
--   entitlements.py:get_news_used_period() uses a NOT EXISTS subquery against
--   newsletters_article_link to exclude newsletter-sourced articles from the
--   direct-article quota count. Without this table, the query errors and
--   get_news_used_period() returns 9999 (fail-closed), blocking ALL news
--   operations for ALL users on audiotours_subscribed.
--
-- IDEMPOTENCY: CREATE TABLE IF NOT EXISTS. Safe to run multiple times.
-- EXECUTION: Must be run INSIDE the audiotours_subscribed database.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS newsletters_article_link (
    id SERIAL PRIMARY KEY,
    newsletters_id INTEGER,
    article_requests_id VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nal_article_requests_id
    ON newsletters_article_link(article_requests_id);

COMMIT;
