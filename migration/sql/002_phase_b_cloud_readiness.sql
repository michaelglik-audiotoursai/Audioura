-- Phase B Cloud Readiness Schema Migration
-- Date: 2026-06-02
-- Purpose: Add columns needed for stateless Cloud Run deployment
-- Safe to run multiple times (IF NOT EXISTS / idempotent)

-- 1. Draft flag for edit-session state across Cloud Run instances
-- When a user does bulk-save, the tour is stored as draft=TRUE.
-- When they promote, draft is flipped to FALSE.
-- This replaces the /app/tours/ filesystem dependency between bulk-save and promote.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'audio_tours' AND column_name = 'draft') THEN
        ALTER TABLE audio_tours ADD COLUMN draft BOOLEAN DEFAULT FALSE;
        RAISE NOTICE 'Added column: audio_tours.draft';
    ELSE
        RAISE NOTICE 'Column audio_tours.draft already exists, skipping';
    END IF;
END $$;

-- Backfill existing tours as non-draft
UPDATE audio_tours SET draft = FALSE WHERE draft IS NULL;

-- 2. Blob storage URI for Phase D (R2 migration)
-- When ZIPs move from PostgreSQL BYTEA to Cloudflare R2,
-- this column stores the R2 object key (e.g., "tours/314.zip").
-- If NULL, the service reads from audio_tour BYTEA (backwards compatible).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'audio_tours' AND column_name = 'tour_blob_uri') THEN
        ALTER TABLE audio_tours ADD COLUMN tour_blob_uri VARCHAR(512);
        RAISE NOTICE 'Added column: audio_tours.tour_blob_uri';
    ELSE
        RAISE NOTICE 'Column audio_tours.tour_blob_uri already exists, skipping';
    END IF;
END $$;

-- 3. Same for news_audios table (news article ZIPs)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'news_audios' AND column_name = 'news_blob_uri') THEN
        ALTER TABLE news_audios ADD COLUMN news_blob_uri VARCHAR(512);
        RAISE NOTICE 'Added column: news_audios.news_blob_uri';
    ELSE
        RAISE NOTICE 'Column news_audios.news_blob_uri already exists, skipping';
    END IF;
END $$;

-- 4. Job status table for ACTIVE_JOBS migration (replaces in-memory dict)
-- This allows multiple Cloud Run instances to track async job status.
CREATE TABLE IF NOT EXISTS job_status (
    job_id VARCHAR(64) PRIMARY KEY,
    service_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress TEXT,
    location TEXT,
    tour_type VARCHAR(50),
    total_stops INTEGER,
    output_data JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for polling by service
CREATE INDEX IF NOT EXISTS idx_job_status_service_created 
    ON job_status (service_name, created_at DESC);

-- Index for cleanup of old jobs
CREATE INDEX IF NOT EXISTS idx_job_status_created 
    ON job_status (created_at);

-- Verify
DO $$
BEGIN
    RAISE NOTICE 'Migration 002_phase_b_cloud_readiness complete';
END $$;
