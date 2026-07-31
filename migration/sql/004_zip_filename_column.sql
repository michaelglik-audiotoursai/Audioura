-- LOCAL-50: Add zip_filename column for deterministic tour→ZIP resolution
-- Date: 2026-07-31
-- Purpose: Eliminate guesswork in find_edit_tour_id() by storing the exact ZIP
--          filename on the audio_tours row at creation time.
-- Safe to run multiple times (IF NOT EXISTS / idempotent)

-- The column stores the bare filename (e.g. "boston_common_walking_a1b2c3d4.zip")
-- NOT a path, NOT an R2 key. This is distinct from tour_blob_uri which stores
-- the R2 object key (e.g. "tours/314.zip").
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'audio_tours' AND column_name = 'zip_filename') THEN
        ALTER TABLE audio_tours ADD COLUMN zip_filename VARCHAR(512);
        RAISE NOTICE 'Added column: audio_tours.zip_filename';
    ELSE
        RAISE NOTICE 'Column audio_tours.zip_filename already exists, skipping';
    END IF;
END $$;

-- Index for lookup by zip_filename (used by resolution service)
CREATE INDEX IF NOT EXISTS idx_audio_tours_zip_filename 
    ON audio_tours (zip_filename) WHERE zip_filename IS NOT NULL;
