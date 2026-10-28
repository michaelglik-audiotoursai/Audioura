-- 057_stop_notes.sql  (LOCAL-795)
--
-- "I like the review page, but no link to leave a note: some people would love
-- to; and some would describe their experience we can potentially use
-- afterwards." (Michael, iPhone, 2026-10-27).
--
-- LOCAL-795 adds, alongside the LOCAL-672 reviews on the orchestrator, a
-- per-STOP free-form note. A listener in the tour player can tap "Tell us about
-- this place" on the current stop and leave up to 500 characters describing
-- their experience of that stop. Unlike a review (LOCAL-672), a note:
--   * is NOT attached to a rating — it is free-form, needs no prior rating, and
--     a listener may leave one for any stop while playing;
--   * is NOT shown publicly in this task (no read endpoint from the app); it is
--     raw material we "can potentially use afterwards" (D727-style: the rules
--     page carries the full wording, no per-note consent checkbox);
--   * carries the stop's INDEX and TITLE as the listener saw them, the tour id,
--     the user id, the language, and created_at.
--
-- Auth/attestation mirror reviews exactly (same orchestrator, same user_id +
-- app-attestation path). The note text runs through the SAME auto-check
-- (profanity / url / contact → held `pending`, else `approved`) so the LEAD
-- queue model is consistent, and a rate limit of 10 notes per user per rolling
-- 24 h (enforced in the service) keeps a single device from flooding the table.
--
-- Translation mapping mirrors tour_ratings/tour_reviews/tour_listens: a
-- translation row (audio_tours.original_tour_id set) shares its SOURCE tour, so
-- the service resolves a translation id to its original before writing and
-- tour_id here is always an ORIGINAL audio_tours.id. The note keeps the
-- listener's own `language` so a note left on the Russian translation is still
-- attributable to Russian even though it keys on the original tour.
--
-- Purely ADDITIVE: no DROP, no DELETE, no change to any existing column's type
-- or default. CREATE TABLE/INDEX IF NOT EXISTS + guarded ALTER ADD COLUMN are
-- idempotent, so applying this twice is a no-op; the service's own self-healing
-- DDL (identical) converges to the same schema whether or not this file was
-- ever run.

BEGIN;

CREATE TABLE IF NOT EXISTS stop_notes (
    id              SERIAL PRIMARY KEY,
    tour_id         INTEGER NOT NULL,            -- references audio_tours.id (an ORIGINAL; translations map to their original_tour_id)
    stop_index      INTEGER NOT NULL,            -- 0-based index of the stop the note is about, as the player reported it
    stop_title      TEXT,                        -- the stop's display title as the listener saw it (NULL when the player had none)
    user_id         VARCHAR(255) NOT NULL,       -- references users.secret_id; the note's author
    note_text       TEXT NOT NULL                -- the listener's words about this stop, <= 500 chars (enforced in the service + here)
                    CHECK (char_length(note_text) <= 500),
    language        VARCHAR(16),                 -- the language the listener was playing (e.g. 'en', 'ru'); NULL when unknown
    note_status     VARCHAR(16) NOT NULL DEFAULT 'pending'   -- pending | approved | rejected (same model as tour_reviews)
                    CHECK (note_status IN ('pending', 'approved', 'rejected')),
    status_reason   TEXT,                        -- why the auto-check held it (profanity | url | contact | ''), for the LEAD queue
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Guarded ADD COLUMN for a table created by an earlier partial run (idempotent;
-- mirrors the service's own self-healing DDL).
ALTER TABLE stop_notes ADD COLUMN IF NOT EXISTS stop_title TEXT;
ALTER TABLE stop_notes ADD COLUMN IF NOT EXISTS language VARCHAR(16);
ALTER TABLE stop_notes ADD COLUMN IF NOT EXISTS note_status VARCHAR(16) NOT NULL DEFAULT 'pending';
ALTER TABLE stop_notes ADD COLUMN IF NOT EXISTS status_reason TEXT;

-- "Notes for this tour (and stop)" — the shape a later private/LEAD read uses,
-- and the key the per-tour write path groups on.
CREATE INDEX IF NOT EXISTS idx_stop_notes_tour_stop
    ON stop_notes(tour_id, stop_index);

-- The rate-limit lookup: "how many notes has this user left in the last 24 h?"
-- keyed on (user_id, created_at).
CREATE INDEX IF NOT EXISTS idx_stop_notes_user_created
    ON stop_notes(user_id, created_at);

COMMENT ON TABLE stop_notes IS
    'LOCAL-795: per-stop free-form listener notes ("Tell us about this place"), '
    'alongside the LOCAL-672 reviews on the orchestrator. Up to 500 chars, run '
    'through the same auto-check (pending|approved|rejected), rate-limited to 10 '
    'per user per 24 h in the service. NOT attached to a rating and NOT shown '
    'publicly in this task — raw material for improving tours. tour_id is always '
    'an ORIGINAL audio_tours.id (a translation maps to its original_tour_id); the '
    'listener language is kept in the language column. Additive; never DELETEs.';

COMMIT;
