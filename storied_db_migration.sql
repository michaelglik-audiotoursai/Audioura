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

-- 6. Venue Corpus Cache (Generic Grounding Phase 2 — degradation ladder + caching)
-- Caches discovered venue data (SPARQL works, site/wiki extraction, story elements)
-- to avoid re-mining on repeat requests. TTL-based invalidation.
-- Note: story_elements_json is a Phase-2 interim; migrates to work-level when SQ-S8 lands.
CREATE TABLE IF NOT EXISTS venue_corpus (
    qid VARCHAR(20) PRIMARY KEY,
    venue_name TEXT NOT NULL,
    official_url TEXT,
    canonical_titles_json JSONB NOT NULL,
    story_elements_json JSONB,
    sparql_works_json JSONB,
    pages_json JSONB,
    language VARCHAR(10),
    tier VARCHAR(10) NOT NULL,  -- rich/medium/thin/unresolvable — NO DEFAULT, always explicit
    corpus_version INT NOT NULL,  -- pipeline version; SQ2+ invalidates stale rows
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_venue_corpus_expires ON venue_corpus(expires_at);
CREATE INDEX IF NOT EXISTS idx_venue_corpus_tier ON venue_corpus(tier);
