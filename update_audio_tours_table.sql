-- SQL script to update the existing audio_tours table

-- Add columns for ZIP file storage and coordinates if they don't exist
ALTER TABLE audio_tours 
ADD COLUMN IF NOT EXISTS audio_tour BYTEA,
ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS number_requested INTEGER NOT NULL DEFAULT 0;

-- Create index on tour_name for faster lookups if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_audio_tours_tour_name ON audio_tours(tour_name);

-- Create index on request_string for faster lookups if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_audio_tours_request_string ON audio_tours(request_string);