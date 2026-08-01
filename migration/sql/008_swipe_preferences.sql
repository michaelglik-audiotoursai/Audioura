-- Migration 008: Swipe-to-sway preference tables
-- LOCAL-101: Capture like/dislike per stop, derive per-user preference vector,
-- bias stop ordering toward preferred content classes.
--
-- Design reference: STORY_QUALITY_DESIGN.md §2c (Beta-count model) + §2d (Subscribed schema)
--
-- Two tables:
--   user_stop_feedback  — raw signal: one row per swipe
--   user_class_prefs    — derived preference vector: one row per user
--
-- The preference model is Beta-count (§2c):
--   α_k, β_k init 1  →  p_k = α_k/(α_k+β_k)
--   Like:    α_k += c_k * 1.0
--   Dislike: α_k unchanged, β_k += c_k * (i_con/5)
--   Cold start: all α=1, β=1 → p=0.5 (neutral, today's behavior exactly)

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════
-- Table 1: Raw swipe signal
-- ═══════════════════════════════════════════════════════════════════════
-- Captures the user's like/dislike AND snapshots the stop's class scores
-- at that moment (so preference derivation doesn't depend on stop_metrics
-- remaining unchanged — the signal is self-contained).

CREATE TABLE IF NOT EXISTS user_stop_feedback (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR(255) NOT NULL,      -- references users.secret_id
    tour_id         INTEGER,                    -- references audio_tours.id (nullable for job-only stops)
    job_id          VARCHAR(255),               -- generation job_id (links to stop_metrics)
    stop_index      INTEGER NOT NULL,           -- which stop in the tour
    swipe           SMALLINT NOT NULL           -- +1 = like, -1 = dislike
                    CHECK (swipe IN (-1, 1)),
    -- Snapshot of the stop's class distribution at swipe time
    class_details   NUMERIC(4,3) NOT NULL,      -- from stop_metrics at swipe time
    class_historic  NUMERIC(4,3) NOT NULL,
    class_social    NUMERIC(4,3) NOT NULL,
    -- i-con score at swipe time (used for dislike weighting per §2c)
    i_con           NUMERIC(3,2) NOT NULL DEFAULT 0.00,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index for user history retrieval and preference recomputation
CREATE INDEX IF NOT EXISTS idx_usf_user_id ON user_stop_feedback(user_id);
-- Index for analytics: how does a specific stop fare across all users
CREATE INDEX IF NOT EXISTS idx_usf_tour_stop ON user_stop_feedback(tour_id, stop_index);

-- ═══════════════════════════════════════════════════════════════════════
-- Table 2: Derived preference vector (materialized, not computed on read)
-- ═══════════════════════════════════════════════════════════════════════
-- One row per user.  Updated after every swipe.
-- α/β are the raw Beta-distribution parameters; p_k = α_k/(α_k+β_k).
-- Confidence = α_k + β_k - 2  (subtracting the prior initialization).
--
-- Michael's interpretability requirement: he can look at a row and read
-- "prefers historical (p=0.72), dislikes social (p=0.31)" directly.

CREATE TABLE IF NOT EXISTS user_class_prefs (
    user_id             VARCHAR(255) PRIMARY KEY,  -- references users.secret_id
    alpha_details       NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    beta_details        NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    alpha_historic      NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    beta_historic       NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    alpha_social        NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    beta_social         NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    -- Materialized preferences (derived, stored for fast reads)
    pref_details        NUMERIC(5,4) NOT NULL DEFAULT 0.5000,
    pref_historic       NUMERIC(5,4) NOT NULL DEFAULT 0.5000,
    pref_social         NUMERIC(5,4) NOT NULL DEFAULT 0.5000,
    -- Bookkeeping
    swipe_count         INTEGER NOT NULL DEFAULT 0,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
