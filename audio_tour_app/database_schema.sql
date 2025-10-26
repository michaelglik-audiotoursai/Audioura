-- New tables to add to existing database

-- Create audio_tours table
CREATE TABLE audio_tours (
    id SERIAL PRIMARY KEY,
    tour_name VARCHAR(255) NOT NULL,
    request_string TEXT NOT NULL,
    audio_tour BYTEA,
    number_requested INTEGER NOT NULL DEFAULT 0,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION
);

-- Create treats table
CREATE TABLE treats (
    id SERIAL PRIMARY KEY,
    ad_name VARCHAR(255) NOT NULL,
    ad_image BYTEA,
    ad_text TEXT,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    distance_in_feet INTEGER NOT NULL DEFAULT 0
);

-- Indexes for geospatial queries
CREATE INDEX idx_audio_tours_location ON audio_tours (lat, lng);
CREATE INDEX idx_treats_location ON treats (lat, lng);