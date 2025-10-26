-- Tour Editing Schema
-- Create tables for custom tours and tour customizations

-- Table to store custom tours (derived from original tours)
CREATE TABLE IF NOT EXISTS custom_tours (
    id SERIAL PRIMARY KEY,
    custom_tour_id VARCHAR(255) UNIQUE NOT NULL, -- e.g., 'custom_123_456'
    original_tour_id INTEGER NOT NULL,
    user_id VARCHAR(255), -- For future user management
    tour_name VARCHAR(255) NOT NULL,
    request_string TEXT NOT NULL,
    audio_tour BYTEA, -- The modified tour ZIP
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    number_requested INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (original_tour_id) REFERENCES audio_tours(id)
);

-- Table to store individual stop customizations
CREATE TABLE IF NOT EXISTS tour_stop_customizations (
    id SERIAL PRIMARY KEY,
    custom_tour_id VARCHAR(255) NOT NULL,
    stop_number INTEGER NOT NULL,
    original_title TEXT,
    custom_title TEXT,
    original_text TEXT,
    custom_text TEXT,
    custom_audio_data BYTEA, -- Base64 decoded audio
    audio_format VARCHAR(10) DEFAULT 'mp3',
    audio_duration INTEGER, -- Duration in seconds
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (custom_tour_id) REFERENCES custom_tours(custom_tour_id),
    UNIQUE(custom_tour_id, stop_number)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_custom_tours_original_id ON custom_tours(original_tour_id);
CREATE INDEX IF NOT EXISTS idx_custom_tours_location ON custom_tours(lat, lng);
CREATE INDEX IF NOT EXISTS idx_tour_stop_customizations_tour ON tour_stop_customizations(custom_tour_id);

-- Add is_custom field to existing queries (we'll handle this in the service)
-- ALTER TABLE audio_tours ADD COLUMN is_custom BOOLEAN DEFAULT FALSE;