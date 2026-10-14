-- 025: an evaluated starting score per tour (LOCAL-685). Additive, idempotent.
-- editor_score 5.0–8.0 replaces the flat 7.5 prior for that tour (shown while
-- unrated, blended with the first 1–3 ratings, Bayesian rank prior).
-- NULL = not scored yet → the old 7.5 applies. Written by tour_editor_score.py.
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS editor_score NUMERIC(3,1)
    CHECK (editor_score IS NULL OR (editor_score >= 5.0 AND editor_score <= 8.0));
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS editor_score_detail JSONB;
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS editor_scored_at TIMESTAMPTZ;
