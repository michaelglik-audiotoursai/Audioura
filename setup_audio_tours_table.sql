-- SQL script to set up the audio_tours table

-- Check if table exists and create if it doesn't
CREATE TABLE IF NOT EXISTS audio_tours (
    id SERIAL PRIMARY KEY,
    tour_name VARCHAR(255) NOT NULL,
    request_string TEXT NOT NULL,
    audio_tour BYTEA,
    number_requested INTEGER NOT NULL DEFAULT 0,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION
);

-- Create index on tour_name for faster lookups
CREATE INDEX IF NOT EXISTS idx_audio_tours_tour_name ON audio_tours(tour_name);

-- Create index on request_string for faster lookups
CREATE INDEX IF NOT EXISTS idx_audio_tours_request_string ON audio_tours(request_string);

-- Grant permissions to admin user
GRANT ALL PRIVILEGES ON TABLE audio_tours TO admin;
GRANT USAGE, SELECT ON SEQUENCE audio_tours_id_seq TO admin;