-- 043: a tour belongs to its track (LOCAL-765 — storied backport of LOCAL-727 /
-- bug 432). Additive, idempotent.
--
-- Problem: after the Subscribed → GCloud Cloud SQL move (D708), Beta, Storied
-- and Subscribed are separate Cloud Run services that SHARE one audio_tours
-- table, each writing its own `track` ('beta' / 'storied' / 'subscribed'). The
-- Storied orchestrator's existing-tour lookup was keyed on lower(tour_name)
-- ALONE, so a Storied store could MATCH and REPLACE a same-name Subscribed (or
-- Beta) row — collapsing it — and a Storied listener could be handed a
-- members-only/paid Subscribed tour for free.
--
-- `track` is per-DEPLOYMENT, not per-request. The LOCAL-765 code change adds
-- `AND track = <this deployment's track>` to the orchestrator's store lookup
-- and post-store re-read, and excludes track='subscribed' from every
-- storied-side read path on audio_tours. This migration only makes the
-- track-scoped lookup FAST; the code is correct even before it runs because the
-- orchestrator self-heals the `track` column.
--
-- Deviation from LOCAL-727 (on the `subscribed` branch): that branch keyed on
-- (lower(tour_name), creator_user_id, track) because it has D678's
-- creator_user_id column. `storied` has NO creator_user_id column in this path,
-- so the key here is (lower(tour_name), track) — track is the only scoping
-- dimension storied has. No Subscribed tables are added here (not storied's
-- concern).
--
-- Ruling (LOCAL-765):
--   1. The existing-tour lookup key becomes (lower(tour_name), track)
--      WHERE original_tour_id IS NULL. A different track (notably 'subscribed')
--      always falls through to INSERT and gets its own row; it is never reused.
--   2. Same name + SAME track still versions the one row (legitimate
--      regeneration), unchanged from before.
--   3. The `track` column already exists (migration 007 / self-healed by the
--      orchestrator and map-delivery, VARCHAR(16) NOT NULL DEFAULT 'beta'); no
--      backfill needed — existing rows are 'beta', correct for pre-Storied data.
--   4. LEAD applies this after the code is merged; this agent tests it only on
--      its own throwaway DB schema. Additive and reversible.

-- 0. Safety: ensure the track column exists (matches the self-heal in the
--    orchestrator and map-delivery). Additive, idempotent; existing rows
--    default to 'beta'.
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS track VARCHAR(16) NOT NULL DEFAULT 'beta';

-- 1. Non-unique index for the per-name, PER-TRACK lookup on originals.
--    Non-unique on purpose: the same name may exist on more than one track
--    (one row each), and a same-track re-generation finds its one row to
--    version it.
CREATE INDEX IF NOT EXISTS idx_audio_tours_name_track
    ON audio_tours (lower(tour_name), track)
    WHERE original_tour_id IS NULL;

-- To REVERSE this migration, run exactly:
--   DROP INDEX IF EXISTS idx_audio_tours_name_track;
