-- Storied v2.2.0 migration
-- All new tables for Storied features. Idempotent (safe to run multiple times).
-- Tables: tour_cache, user_preferences, shared_tours, referral_codes, referral_redemptions

-- 1. Tour Cache (from tour_cache_layer1.py, task #19)
CREATE TABLE IF NOT EXISTS tour_cache (
    cache_key VARCHAR(64) PRIMARY KEY,
    location TEXT NOT NULL,
    tour_type TEXT NOT NULL,
    total_stops INTEGER NOT NULL,
    tour_content TEXT NOT NULL,
    spine_json TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    hit_count INTEGER DEFAULT 0
);

-- 2. User Preferences (from persona_preference_store.py, task #44)
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    persona TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. Shared Tours (from tour_sharing.py, task #48)
CREATE TABLE IF NOT EXISTS shared_tours (
    tour_id VARCHAR(8) PRIMARY KEY,
    tour_text TEXT NOT NULL,
    location TEXT NOT NULL,
    tour_type TEXT NOT NULL,
    total_stops INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    share_count INTEGER DEFAULT 0
);

-- 4. Referral Codes (from referral_engine.py, task #51)
CREATE TABLE IF NOT EXISTS referral_codes (
    code VARCHAR(6) PRIMARY KEY,
    referrer_user_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    redemption_count INTEGER DEFAULT 0
);

-- 5. Referral Redemptions (from referral_engine.py, task #51)
CREATE TABLE IF NOT EXISTS referral_redemptions (
    id SERIAL PRIMARY KEY,
    referral_code VARCHAR(6) NOT NULL REFERENCES referral_codes(code),
    new_user_id TEXT NOT NULL,
    redeemed_at TIMESTAMP DEFAULT NOW()
);

-- Verification
-- [S85] Add storied_mode column to audio_tours table (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audio_tours' AND column_name = 'storied_mode'
    ) THEN
        ALTER TABLE audio_tours ADD COLUMN storied_mode BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

SELECT 'storied_migration_complete' AS status;
