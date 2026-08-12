-- Track B: bring Cloud SQL (production Beta, api.audioura.com) up to schema
-- parity with local dev, so the Storied Cloud Run service (which runs current
-- storied-branch code) has every table/column it needs to write to.
-- Date: 2026-08-11
-- Context: DECISIONS.md D347. Cloud SQL was last synced ~2026-06-25 and is
-- missing 23 tables plus 5 audio_tours columns that have shipped since via
-- Mac Mini local-dev migrations (migration/sql/002-006, 008-009) that were
-- never applied here. This file brings it current in one additive pass.
-- Safe to run multiple times (IF NOT EXISTS throughout). Adds nothing that
-- writes to or reads from existing rows except the audio_tours ADD COLUMNs,
-- which are all nullable or defaulted.

-- ── audio_tours: 5 missing columns ─────────────────────────────────────────
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS storied_mode boolean DEFAULT false;
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS i_con_avg numeric(3,2);
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS i_con_min numeric(3,2);
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS zip_filename character varying(512);
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS is_test boolean DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_audio_tours_zip_filename
    ON audio_tours (zip_filename) WHERE (zip_filename IS NOT NULL);

-- Note: uq_audio_tours_original_name (unique on lower(tour_name) WHERE
-- original_tour_id IS NULL) is intentionally NOT created here — applying it
-- against 302 live rows risks a duplicate-title violation aborting the
-- migration. Apply separately once the row set is confirmed clean.

-- ── Missing tables (23), grouped as in tests/schema_audiotours.sql ────────

CREATE TABLE IF NOT EXISTS cost_ledger (
    id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    operation_type character varying(64) NOT NULL,
    user_id character varying(128),
    our_cost_usd numeric(12,6) NOT NULL,
    cache_hit boolean DEFAULT false NOT NULL,
    job_id character varying(128),
    breakdown jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    description character varying(256)
);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_job ON cost_ledger (job_id);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_operation_type ON cost_ledger (operation_type, created_at);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_user_time ON cost_ledger (user_id, created_at);

CREATE TABLE IF NOT EXISTS domain_tier_cache (
    domain character varying(255) NOT NULL PRIMARY KEY,
    tier character varying(10) NOT NULL,
    checked_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_domain_tier_expires ON domain_tier_cache (expires_at);

CREATE TABLE IF NOT EXISTS low_balance_events (
    id serial PRIMARY KEY,
    user_id character varying(255) NOT NULL REFERENCES users(secret_id) ON DELETE CASCADE,
    current_balance_usd numeric(10,4) NOT NULL,
    threshold_usd numeric(10,4) NOT NULL,
    acknowledged boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_low_balance_pending ON low_balance_events (user_id, acknowledged) WHERE (acknowledged = false);

CREATE TABLE IF NOT EXISTS news_cache (
    cache_key character varying(64) NOT NULL PRIMARY KEY,
    article_id character varying(255) NOT NULL,
    article_text_hash character varying(64) NOT NULL,
    major_points_count integer DEFAULT 0 NOT NULL,
    request_string text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    hit_count integer DEFAULT 0,
    content_length integer DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_news_cache_article_id ON news_cache (article_id);
CREATE INDEX IF NOT EXISTS idx_news_cache_created_at ON news_cache (created_at);

CREATE TABLE IF NOT EXISTS referral_codes (
    code character varying(6) NOT NULL PRIMARY KEY,
    referrer_user_id text NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    redemption_count integer DEFAULT 0
);

CREATE TABLE IF NOT EXISTS referral_redemptions (
    id serial PRIMARY KEY,
    referral_code character varying(6) NOT NULL REFERENCES referral_codes(code),
    new_user_id text NOT NULL,
    redeemed_at timestamp without time zone DEFAULT now(),
    CONSTRAINT uq_referral_redemptions_code_user UNIQUE (referral_code, new_user_id)
);

CREATE TABLE IF NOT EXISTS revenuecat_webhook_events (
    event_id character varying(256) NOT NULL PRIMARY KEY,
    event_type character varying(64) NOT NULL,
    user_id character varying(256) NOT NULL,
    product_id character varying(256),
    processed_at timestamp with time zone DEFAULT now() NOT NULL,
    payload_hash character varying(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS shared_tours (
    tour_id character varying(8) NOT NULL PRIMARY KEY,
    tour_text text NOT NULL,
    location text NOT NULL,
    tour_type text NOT NULL,
    total_stops integer NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    share_count integer DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stop_corpus (
    id serial PRIMARY KEY,
    venue_name text NOT NULL,
    stop_title text NOT NULL,
    passages_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    source_pages jsonb DEFAULT '[]'::jsonb NOT NULL,
    passage_count integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    passage_roles jsonb,
    CONSTRAINT stop_corpus_venue_name_stop_title_key UNIQUE (venue_name, stop_title)
);
CREATE INDEX IF NOT EXISTS idx_stop_corpus_stop ON stop_corpus (stop_title);
CREATE INDEX IF NOT EXISTS idx_stop_corpus_venue ON stop_corpus (venue_name);

CREATE TABLE IF NOT EXISTS stop_metrics (
    id serial PRIMARY KEY,
    job_id character varying(50),
    tour_id integer REFERENCES audio_tours(id) ON DELETE CASCADE,
    stop_index integer NOT NULL,
    stop_title character varying(255),
    i_con numeric(3,2),
    class_details numeric(4,3),
    class_historic numeric(4,3),
    class_social numeric(4,3),
    paragraphs jsonb,
    evaluator_version character varying(20) DEFAULT '1.0.0'::character varying,
    prompt_hash character varying(12),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    verified boolean DEFAULT true
);
CREATE INDEX IF NOT EXISTS idx_stop_metrics_job_id ON stop_metrics (job_id);
CREATE INDEX IF NOT EXISTS idx_stop_metrics_tour_id ON stop_metrics (tour_id);

CREATE TABLE IF NOT EXISTS subscription_transactions (
    id serial PRIMARY KEY,
    user_id character varying(255) NOT NULL REFERENCES users(secret_id) ON DELETE CASCADE,
    transaction_type character varying(30) NOT NULL,
    transaction_id character varying(100),
    operation_type character varying(50),
    our_cost_usd numeric(10,6),
    user_charge_usd numeric(10,4),
    resulting_balance_usd numeric(10,4),
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sub_txn_type ON subscription_transactions (transaction_type);
CREATE INDEX IF NOT EXISTS idx_sub_txn_user_created ON subscription_transactions (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS subscriptions (
    id serial PRIMARY KEY,
    user_id character varying(255) NOT NULL REFERENCES users(secret_id) ON DELETE CASCADE,
    tier character varying(20) NOT NULL,
    state character varying(20) DEFAULT 'active'::character varying NOT NULL,
    period_start timestamp without time zone NOT NULL,
    period_end timestamp without time zone NOT NULL,
    provider_subscription_id character varying(255),
    credit_balance_usd numeric(10,4) DEFAULT 0.0,
    cost_used_this_period_usd numeric(10,4) DEFAULT 0.0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT subscriptions_state_check CHECK (((state)::text = ANY ((ARRAY['active'::character varying, 'lapsed'::character varying, 'cancelled'::character varying, 'billing_retry'::character varying])::text[]))),
    CONSTRAINT subscriptions_tier_check CHECK (((tier)::text = ANY ((ARRAY['ppu'::character varying, 'unlimited'::character varying])::text[])))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_active_user ON subscriptions (user_id) WHERE ((state)::text = ANY ((ARRAY['active'::character varying, 'billing_retry'::character varying])::text[]));
CREATE INDEX IF NOT EXISTS idx_subscriptions_provider_id ON subscriptions (provider_subscription_id);

CREATE TABLE IF NOT EXISTS tour_cache (
    cache_key character varying(64) NOT NULL PRIMARY KEY,
    location text NOT NULL,
    tour_type text NOT NULL,
    total_stops integer NOT NULL,
    tour_content text NOT NULL,
    spine_json text,
    created_at timestamp without time zone DEFAULT now(),
    hit_count integer DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tour_scores (
    id serial PRIMARY KEY,
    tour_id integer,
    tour_name text,
    scored_at timestamp with time zone DEFAULT now() NOT NULL,
    code_sha character varying(12),
    n_requested integer NOT NULL,
    n_delivered integer NOT NULL,
    base_score real NOT NULL,
    structural real NOT NULL,
    correlation real NOT NULL,
    venue_identity real NOT NULL,
    total real NOT NULL,
    per_stop jsonb NOT NULL,
    scorer_version character varying(64) NOT NULL,
    scoring_ms real,
    is_rescore boolean DEFAULT false NOT NULL,
    previous_score_id integer,
    delta jsonb
);
CREATE INDEX IF NOT EXISTS idx_tour_scores_tour_id ON tour_scores (tour_id);

CREATE TABLE IF NOT EXISTS usage_counters (
    id serial PRIMARY KEY,
    user_id character varying(64) NOT NULL,
    period_key character varying(20) NOT NULL,
    kind character varying(20) NOT NULL,
    count integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT usage_counters_user_id_period_key_kind_key UNIQUE (user_id, period_key, kind)
);
CREATE INDEX IF NOT EXISTS idx_usage_counters_user_period ON usage_counters (user_id, period_key);

CREATE TABLE IF NOT EXISTS user_class_prefs (
    user_id character varying(255) NOT NULL PRIMARY KEY,
    alpha_details numeric(8,4) DEFAULT 1.0 NOT NULL,
    beta_details numeric(8,4) DEFAULT 1.0 NOT NULL,
    alpha_historic numeric(8,4) DEFAULT 1.0 NOT NULL,
    beta_historic numeric(8,4) DEFAULT 1.0 NOT NULL,
    alpha_social numeric(8,4) DEFAULT 1.0 NOT NULL,
    beta_social numeric(8,4) DEFAULT 1.0 NOT NULL,
    pref_details numeric(5,4) DEFAULT 0.5000 NOT NULL,
    pref_historic numeric(5,4) DEFAULT 0.5000 NOT NULL,
    pref_social numeric(5,4) DEFAULT 0.5000 NOT NULL,
    swipe_count integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id text NOT NULL PRIMARY KEY,
    persona text NOT NULL,
    updated_at timestamp without time zone DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_stop_feedback (
    id serial PRIMARY KEY,
    user_id character varying(255) NOT NULL,
    tour_id integer,
    job_id character varying(255),
    stop_index integer NOT NULL,
    swipe smallint NOT NULL,
    class_details numeric(4,3) NOT NULL,
    class_historic numeric(4,3) NOT NULL,
    class_social numeric(4,3) NOT NULL,
    i_con numeric(3,2) DEFAULT 0.00 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT user_stop_feedback_swipe_check CHECK ((swipe = ANY (ARRAY[(-1), 1])))
);
CREATE INDEX IF NOT EXISTS idx_usf_tour_stop ON user_stop_feedback (tour_id, stop_index);
CREATE INDEX IF NOT EXISTS idx_usf_user_id ON user_stop_feedback (user_id);

CREATE TABLE IF NOT EXISTS venue_corpus (
    qid character varying(20) NOT NULL PRIMARY KEY,
    venue_name text NOT NULL,
    official_url text,
    canonical_titles_json jsonb NOT NULL,
    story_elements_json jsonb,
    sparql_works_json jsonb,
    pages_json jsonb,
    language character varying(10),
    tier character varying(20) NOT NULL,
    corpus_version integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_venue_corpus_expires ON venue_corpus (expires_at);
CREATE INDEX IF NOT EXISTS idx_venue_corpus_tier ON venue_corpus (tier);

CREATE TABLE IF NOT EXISTS wallet_balance_cache (
    user_id character varying(128) NOT NULL PRIMARY KEY,
    balance_cents integer DEFAULT 0 NOT NULL,
    last_ledger_id uuid,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS wallet_ledger (
    id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    user_id character varying(128) NOT NULL,
    movement_type character varying(64) NOT NULL,
    amount_cents integer NOT NULL,
    balance_after_cents integer NOT NULL,
    idempotency_key character varying(256) NOT NULL,
    description text,
    reference_id character varying(256),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ledger_idempotency ON wallet_ledger (idempotency_key);
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_reference ON wallet_ledger (reference_id);
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_time ON wallet_ledger (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS wallet_subscription (
    user_id character varying(128) NOT NULL PRIMARY KEY,
    tier character varying(32) DEFAULT 'free'::character varying NOT NULL,
    period_start timestamp with time zone,
    period_end timestamp with time zone,
    monthly_cost_spent_cents integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS work_stories (
    id serial PRIMARY KEY,
    work_key character varying(512) NOT NULL UNIQUE,
    work_qid character varying(20),
    title text NOT NULL,
    artist text,
    core_data jsonb NOT NULL,
    elements_json jsonb,
    sources_json jsonb,
    query_log jsonb,
    core_expires_at timestamp without time zone NOT NULL,
    elements_expires_at timestamp without time zone NOT NULL,
    corpus_version integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_work_stories_expires ON work_stories (elements_expires_at);
CREATE INDEX IF NOT EXISTS idx_work_stories_qid ON work_stories (work_qid) WHERE (work_qid IS NOT NULL);
