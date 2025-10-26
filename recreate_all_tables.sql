-- Recreate all tables for the AudioTours application

-- Create audio_tours table
CREATE TABLE IF NOT EXISTS audio_tours (
    id SERIAL PRIMARY KEY,
    tour_name VARCHAR(255) NOT NULL,
    request_string TEXT NOT NULL,
    audio_tour BYTEA,
    number_requested INTEGER NOT NULL DEFAULT 0,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create treats table
CREATE TABLE IF NOT EXISTS treats (
    id SERIAL PRIMARY KEY,
    ad_name VARCHAR(255) NOT NULL,
    ad_image BYTEA,
    ad_text TEXT,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    distance_in_feet INTEGER NOT NULL DEFAULT 0
);

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    secret_id VARCHAR(255) PRIMARY KEY,
    app_version VARCHAR(50) DEFAULT 'unknown',
    is_deleted BOOLEAN DEFAULT FALSE,
    app_uninstalled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Create coordinates table
CREATE TABLE IF NOT EXISTS coordinates (
    id SERIAL PRIMARY KEY,
    secret_id VARCHAR(255) REFERENCES users(secret_id),
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create tour_requests table
CREATE TABLE IF NOT EXISTS tour_requests (
    id SERIAL PRIMARY KEY,
    secret_id VARCHAR(255) REFERENCES users(secret_id),
    tour_id VARCHAR(255),
    request_string TEXT,
    status VARCHAR(50) DEFAULT 'started',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create map_requests table
CREATE TABLE IF NOT EXISTS map_requests (
    id SERIAL PRIMARY KEY,
    secret_id VARCHAR(255) REFERENCES users(secret_id),
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for geospatial queries
CREATE INDEX IF NOT EXISTS idx_audio_tours_location ON audio_tours (lat, lng);
CREATE INDEX IF NOT EXISTS idx_treats_location ON treats (lat, lng);
CREATE INDEX IF NOT EXISTS idx_audio_tours_tour_name ON audio_tours(tour_name);
CREATE INDEX IF NOT EXISTS idx_audio_tours_request_string ON audio_tours(request_string);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO admin;