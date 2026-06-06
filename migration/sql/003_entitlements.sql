-- Entitlements Schema (data-driven, no hardcoded limits)
-- Plans table stores all tier limits as rows — change with UPDATE, not code deploy.

CREATE TABLE IF NOT EXISTS plans (
    plan_id VARCHAR(20) PRIMARY KEY,
    tours_per_day INTEGER NOT NULL DEFAULT 1,
    tour_max_poi INTEGER NOT NULL DEFAULT 30,
    tour_max_minutes INTEGER NOT NULL DEFAULT 120,
    news_per_period INTEGER NOT NULL DEFAULT 10,
    news_period VARCHAR(10) NOT NULL DEFAULT 'day',  -- 'day' or 'month'
    news_max_minutes INTEGER NOT NULL DEFAULT 10,
    downloads_unlimited BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed the free plan
INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
VALUES ('free', 1, 30, 120, 10, 'day', 10, TRUE)
ON CONFLICT (plan_id) DO NOTHING;

-- Add plan column to users (if users table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'plan') THEN
            ALTER TABLE users ADD COLUMN plan VARCHAR(20) DEFAULT 'free' REFERENCES plans(plan_id);
            RAISE NOTICE 'Added plan column to users table';
        END IF;
    END IF;
END $$;

-- Usage tracking table (lightweight, for when derived counts get slow)
CREATE TABLE IF NOT EXISTS usage_counters (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    period_key VARCHAR(20) NOT NULL,  -- e.g. '2026-06-03' for daily, '2026-06' for monthly
    kind VARCHAR(20) NOT NULL,        -- 'tour_generation', 'news_article'
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, period_key, kind)
);

CREATE INDEX IF NOT EXISTS idx_usage_counters_user_period ON usage_counters(user_id, period_key);
