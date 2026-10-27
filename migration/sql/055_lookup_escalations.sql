-- 055_lookup_escalations.sql  (LOCAL-784, D722)
--
-- Michael, 2026-10-26 (D722): LOCAL-779B refused "Middle Eastern restaurants near
-- me, West Roxbury" because the free OSM tool found nothing, while Google lists
-- three (Al Wadi, Stardust, Bread Thyme). "If the cheap tools find nothing, try a
-- dearer one before refusing. If it really is nothing we spent little; if it was
-- our mistake we avoided an embarrassment. Record each case and learn from it."
--
-- escalating_lookup.py runs a ladder before any "nothing found": tier (a) the
-- current cheap path → tier (b) Serper Places with `ll` (LOCAL-783) → tier (c)
-- Gemini with Google-Search grounding, each tier-c name re-verified on Places /
-- geocode inside the scope. It stops at the first tier that yields >= `needed`
-- verified results, under a per-request $0.10 escalation budget metered through
-- `_meter`.
--
-- WHAT THIS ADDS, PURELY ADDITIVELY (no DROP, no DELETE, no column retype):
--
--   lookup_escalations — one row per escalation EVENT. Written whenever a dearer
--     tier (b or c) found what a cheaper tier missed (so a free-OSM miss that
--     Serper/Google rescued is visible and billable), AND whenever ALL tiers
--     found nothing (tier_found='none', so a genuine absence is visible too —
--     the honest refusals that stay honest). `results_by_tier` is a JSON map
--     {a:[names], b:[names], c:[names]} so the report can show WHAT each tier
--     returned. `cost_usd` is the escalation's metered spend (Serper + grounded
--     Gemini for this request only). A tier-a hit (the cheap path already
--     sufficed) writes NO row — there was no escalation to record.
--
--   lookup_routing — learned routing. One row per (category, region_key) where
--     region_key is a geohash-5 of the scope centre (~5 km cell). `misses_7d`
--     counts how many times the cheap tier (a) missed for that cell in the last
--     7 days; once it is >= 3 the ladder STARTS at `start_tier` (the tier that
--     worked), skipping the known-empty cheap call. Every row is REVERSIBLE:
--     deleting it restores the default (start at tier a) with no code change —
--     it is a LEAD lever, never a code path. The composite PK makes an upsert on
--     (category, region_key) idempotent.
--
-- A (category, region_key) with NO lookup_routing row behaves exactly as today:
-- the ladder starts at tier a. The table only ever promotes a start tier it can
-- justify from >= 3 recent misses; it never withholds the cheap tier it has not
-- yet seen fail.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS and a
-- guarded CHECK, wrapped in one transaction. Applying it twice is a no-op; the
-- module's own self-healing DDL (identical) converges to the same schema whether
-- or not this file was ever run. Applying it adds two tables, never a row.

BEGIN;

CREATE TABLE IF NOT EXISTS lookup_escalations (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    user_id         TEXT,                   -- device secret_id / listener id, when known
    request         TEXT,                   -- the user's request / location string
    kind            TEXT,                   -- 'dining' | 'business' | 'by_reference'
    category        TEXT,                   -- the routing category (cuisine / poi class)
    scope           TEXT,                   -- the resolved scope text ("West Roxbury, MA")
    scope_lat       DOUBLE PRECISION,       -- scope centre latitude, when geocoded
    scope_lng       DOUBLE PRECISION,       -- scope centre longitude, when geocoded
    tier_found      TEXT         NOT NULL,  -- 'a' | 'b' | 'c' | 'none' — tier that satisfied, or none
    results_by_tier JSONB        NOT NULL DEFAULT '{}'::jsonb, -- {a:[names], b:[names], c:[names]}
    cost_usd        NUMERIC(12,6) NOT NULL DEFAULT 0.0         -- metered escalation spend for this request
);

-- The report reads "everything since <when>" and groups by (kind, category,
-- tier_found) — index the time axis (the --since window and recency) and the
-- grouping axis.
CREATE INDEX IF NOT EXISTS idx_lookup_escalations_ts
    ON lookup_escalations (ts DESC);
CREATE INDEX IF NOT EXISTS idx_lookup_escalations_group
    ON lookup_escalations (kind, category, tier_found, ts DESC);

-- Guard the closed vocabulary tier_found relies on. Added guarded so a re-run
-- does not error on an already-present constraint; the table is new so no
-- existing row can violate it.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_lookup_escalations_tier'
    ) THEN
        ALTER TABLE lookup_escalations
            ADD CONSTRAINT chk_lookup_escalations_tier
            CHECK (tier_found IN ('a', 'b', 'c', 'none'));
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS lookup_routing (
    category     TEXT         NOT NULL,     -- routing category (cuisine / poi class)
    region_key   TEXT         NOT NULL,     -- geohash-5 of the scope centre (~5 km cell)
    start_tier   TEXT         NOT NULL DEFAULT 'a', -- tier the ladder STARTS at ('a'|'b'|'c')
    misses_7d    INTEGER      NOT NULL DEFAULT 0,   -- cheap-tier misses for this cell in 7 days
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (category, region_key)
);

-- The ladder reads one row per (category, region_key) at the start of a lookup —
-- the PK covers that. A recency index supports a LEAD sweep of recently-promoted
-- cells.
CREATE INDEX IF NOT EXISTS idx_lookup_routing_updated
    ON lookup_routing (updated_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_lookup_routing_start_tier'
    ) THEN
        ALTER TABLE lookup_routing
            ADD CONSTRAINT chk_lookup_routing_start_tier
            CHECK (start_tier IN ('a', 'b', 'c'));
    END IF;
END$$;

COMMENT ON TABLE lookup_escalations IS
    'LOCAL-784/D722: one row per escalation EVENT in escalating_lookup. Written '
    'when a dearer tier (b/c) found what a cheaper tier missed, and when ALL '
    'tiers found nothing (tier_found=none, so real absences are visible). '
    'results_by_tier = {a:[names],b:[names],c:[names]}; cost_usd = metered '
    'escalation spend for the request. A tier-a hit writes no row. Read by '
    'escalation_report.py.';

COMMENT ON TABLE lookup_routing IS
    'LOCAL-784/D722: learned routing. One row per (category, region_key=geohash-5 '
    'of the scope centre). When misses_7d >= 3 the ladder STARTS at start_tier, '
    'skipping the known-empty cheap call. Every row is REVERSIBLE — deleting it '
    'restores start-at-tier-a with no code change (a LEAD lever, never a code '
    'path). A (category, region_key) with no row behaves as today (starts at a).';

COMMIT;

-- Verify:
-- SELECT count(*) FROM lookup_escalations;   -- 0 on a fresh DB
-- SELECT count(*) FROM lookup_routing;       -- 0 on a fresh DB
-- \d lookup_escalations                        -- 10 columns + 2 indexes + 1 check
-- \d lookup_routing                            -- 5 columns + PK + 1 index + 1 check
