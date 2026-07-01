-- Storied v2.2.0: Add storied_mode column to audio_tours table
-- Tracks which tours were generated in Storied mode vs Beta mode.
-- Idempotent: safe to run multiple times.

-- Add storied_mode column (defaults to false for all existing Beta tours)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audio_tours' AND column_name = 'storied_mode'
    ) THEN
        ALTER TABLE audio_tours ADD COLUMN storied_mode BOOLEAN DEFAULT false;
    END IF;
END $$;

-- Add generation_spine_json column (stores the spine used for Storied tours)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audio_tours' AND column_name = 'generation_spine_json'
    ) THEN
        ALTER TABLE audio_tours ADD COLUMN generation_spine_json TEXT;
    END IF;
END $$;

-- Add persona column (stores the persona used for generation, if any)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audio_tours' AND column_name = 'generation_persona'
    ) THEN
        ALTER TABLE audio_tours ADD COLUMN generation_persona VARCHAR(50);
    END IF;
END $$;

-- Verification
SELECT 'storied_audio_tours_migration_complete' AS status;
