-- 056_stop_pool_rejected.sql  (LOCAL-792, D726 as amended by Michael 2026-10-27)
--
-- "Why do we keep incorrect material for future usage?" (Michael). The stop pool
-- (LOCAL-590, `stop_pool`) keeps whatever a delivered tour contained; nothing
-- ever marks a stop BAD. Tour 463 (War Remnants Museum, Subscribed Preview) then
-- reused two bad stops — a news headline ("Khai mạc Hội thảo Quốc tế …") and a
-- fabricated "Interesting"/"Balcony"-style entry — because the pool had no notion
-- of "this stop is incorrect; never reuse it".
--
-- D726 (amended) rules THREE cases three different ways:
--   * OUT OF SCOPE for THIS tour (real place, just too far / not on the route) —
--     SKIP for this tour only (LOCAL-788 `_revalidate_pooled_scope`); it stays in
--     the pool because it is good material for the tour it belongs to (Byblos is
--     a valid Norwood stop). NOT moved here.
--   * WRONG PIN (real place, good research, wrong coordinates) — the coordinates
--     are corrected IN PLACE (`fix_stop_coords.py`); the stop stays in the pool.
--     NOT moved here.
--   * INCORRECT CONTENT (not a place / not this venue / wrong facts) — the row is
--     MOVED OUT of `stop_pool`: copied here (all columns + reason/by/at/source
--     tour), then removed from `stop_pool`. The pool then holds only good
--     material; the evidence lives OUTSIDE it for the failure analysis (D723).
--   * FILED UNDER THE WRONG VENUE — re-filed under its own venue identity when it
--     resolves to one place; otherwise treated as incorrect content (moved here).
--
-- WHAT THIS ADDS, PURELY ADDITIVELY (no DROP, no DELETE, no column retype):
--
--   stop_pool_rejected — a quarantine table that is `stop_pool`'s columns EXACTLY
--     (same names/types, same PRIMARY KEY (pool_key, title_norm) so a moved row
--     keeps its identity and a second move of the same stop is a no-op upsert)
--     PLUS four provenance-of-rejection columns:
--       reject_reason   text        — why it was moved (junk title, other venue,
--                                      news headline, fabricated fact, …)
--       rejected_by     text        — who moved it (a person, or an automatic
--                                      source such as 'auto:junk_title_guard')
--       rejected_at     timestamptz — when (DEFAULT NOW())
--       source_tour_id  int         — the audio_tours.id the rejection came from
--                                      (the tour whose reuse surfaced the bad
--                                      stop), NULL when not attributable.
--
-- A row only ever arrives here via `reject_stops.py --apply` (manual) or the
-- automatic junk-title / other-venue reject in the reuse path — and ONLY after
-- its copy here is verified, in ONE transaction, before the `stop_pool` delete.
-- `reject_stops.py --restore` moves a row back (here → stop_pool) intact. This
-- migration itself DELETEs nothing and never touches audio_tours.
--
-- The LOCAL-778 miner (reads delivered tours back into the pool) and every reuse
-- read (`stop_pool_store.get_pool_stops`) now SKIP any (pool_key, title_norm)
-- present here, so a rejected stop can never re-enter the pool from a delivered
-- tour nor be returned to a reuse — belt-and-braces on top of the row's removal.
--
-- Idempotent: CREATE TABLE/INDEX IF NOT EXISTS + guarded ALTER ADD COLUMN, in one
-- transaction. The reject tool's own self-healing DDL (identical) converges to
-- the same schema whether or not this file was ever run. Applying it twice is a
-- no-op.

BEGIN;

CREATE TABLE IF NOT EXISTS stop_pool_rejected (
    -- ── stop_pool columns, verbatim (so a moved row is a straight column copy) ──
    pool_key            TEXT        NOT NULL,
    title_norm          TEXT        NOT NULL,
    venue_identity      TEXT        NOT NULL,
    tour_type           TEXT        NOT NULL,
    pool_version        INTEGER     NOT NULL,
    title               TEXT        NOT NULL,
    artist              TEXT        DEFAULT '',
    year                TEXT        DEFAULT '',
    narration           TEXT        NOT NULL,
    raw_block           TEXT,
    address             TEXT        DEFAULT '',
    coordinates         TEXT        DEFAULT '',
    type_specialty      TEXT        DEFAULT '',
    specific_examples   TEXT        DEFAULT '',
    operational_details TEXT        DEFAULT '',
    sources_json        TEXT,
    story_elements_json TEXT,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hit_count           INTEGER     DEFAULT 0,
    order_seq           INTEGER     DEFAULT 0,
    research_cost_usd   NUMERIC(12, 6) DEFAULT 0,
    stop_record_json    TEXT,
    news_generated_at   TIMESTAMPTZ,
    -- ── rejection provenance (LOCAL-792) ──────────────────────────────────────
    reject_reason       TEXT,
    rejected_by         TEXT,
    rejected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_tour_id      INTEGER,
    PRIMARY KEY (pool_key, title_norm)
);

-- Guarded ADD COLUMN for a table created by an earlier partial run (idempotent;
-- mirrors stop_pool_store's own self-healing migrations).
ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS order_seq INTEGER DEFAULT 0;
ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS research_cost_usd NUMERIC(12, 6) DEFAULT 0;
ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS stop_record_json TEXT;
ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS news_generated_at TIMESTAMPTZ;
ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS reject_reason TEXT;
ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS rejected_by TEXT;
ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS source_tour_id INTEGER;

-- "Which (venue identity, normalized title) are rejected?" — the lookup the
-- LOCAL-778 miner and every reuse read use to skip a quarantined stop. Keyed by
-- the same (pool_key, title_norm) the pool itself is keyed by.
CREATE INDEX IF NOT EXISTS idx_stop_pool_rejected_key
    ON stop_pool_rejected (pool_key);
CREATE INDEX IF NOT EXISTS idx_stop_pool_rejected_identity
    ON stop_pool_rejected (venue_identity, title_norm);

COMMENT ON TABLE stop_pool_rejected IS
    'LOCAL-792/D726 (amended, Michael 2026-10-27): quarantine for INCORRECT stops '
    'moved OUT of stop_pool (not a place / not this venue / wrong facts). Same '
    'columns as stop_pool plus reject_reason, rejected_by, rejected_at, '
    'source_tour_id. A row arrives only via reject_stops.py --apply or the '
    'automatic junk-title/other-venue reject, and ONLY after its copy here is '
    'verified before the stop_pool delete; --restore moves it back. Far-away '
    'stops are NOT moved here (LOCAL-788 skip-only); wrong-pin stops are fixed in '
    'place (fix_stop_coords.py). The miner and every reuse read skip any '
    '(pool_key, title_norm) present here. Additive; never DELETEs; never touches '
    'audio_tours.';

COMMIT;
