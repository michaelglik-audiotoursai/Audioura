-- I-CON: per-stop informational-context scoring + classification
-- Additive + nullable only (Beta parity: STORIED_MODE=false never touches these)
-- Run: psql -U postgres -d audioura -f icon_migration.sql

CREATE TABLE IF NOT EXISTS stop_metrics (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(50),
    tour_id INTEGER REFERENCES audio_tours(id) ON DELETE CASCADE,
    stop_index INTEGER NOT NULL,
    stop_title VARCHAR(255),
    i_con NUMERIC(3,2),
    class_details NUMERIC(4,3),
    class_historic NUMERIC(4,3),
    class_social NUMERIC(4,3),
    paragraphs JSONB,  -- [{text, i_con, class_dist, flags[]}]
    evaluator_version VARCHAR(20) DEFAULT '1.0.0',
    prompt_hash VARCHAR(12),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tour-level aggregates (nullable — only populated when STORIED_MODE=true)
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS i_con_avg NUMERIC(3,2);
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS i_con_min NUMERIC(3,2);

-- Index for efficient lookup by tour
CREATE INDEX IF NOT EXISTS idx_stop_metrics_tour_id ON stop_metrics(tour_id);
CREATE INDEX IF NOT EXISTS idx_stop_metrics_job_id ON stop_metrics(job_id);
