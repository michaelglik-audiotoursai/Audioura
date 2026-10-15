-- 035_community_tours.sql  (LOCAL-701, D663 §2 + §3)
--
-- Two additive, idempotent changes, wrapped in one transaction. Applying twice
-- is a no-op (UPDATE is value-asserting; ADD COLUMN / CREATE INDEX use IF NOT
-- EXISTS). NO DROP, NO DELETE, NO column retype.
--
-- D663 §2 — WHO MAY CHARGE. "Everyone who can create tours may charge" — not
--   only the Curator. plans.can_sell becomes TRUE for l2 (Free), l3 ($10 Pack),
--   l4 (Curator, already TRUE from migration 012) and tester. l1 (Introduction)
--   stays FALSE: it cannot create tours, so it cannot sell. This overrules the
--   Curator-only selling of D652/LOCAL-677. The guide's Price control and the
--   community paid-pass options appear for any plan with can_sell, so widening
--   the flag is the whole mechanism — tour_pricing_service.is_curator and
--   communities already read plans.can_sell as DATA, not a hard-coded level.
--
--   LEAD applies this UPDATE to the shared dev DB (SUBMISSION note). This file
--   is tested on the test DB only; the code-side seed in migration 012 is
--   updated in lock-step (l2/l3/tester seeds now carry can_sell = TRUE) so a
--   FRESH database created from the migrations matches without this UPDATE.
--
-- D663 §3 — A TOUR MADE FOR A COMMUNITY. A generated tour can belong to a
--   community. Two additive columns on audio_tours carry that:
--     community_id          — the owning community (NULL = an ordinary public
--                             tour, exactly as today). FK to communities(id);
--                             ON DELETE SET NULL so removing a community never
--                             deletes the tours (they just stop being community
--                             tours — the generator still charged the organiser).
--     community_visibility  — 'members' (default) or 'public'. members: never on
--                             /tours-near or /search-tours, only on the community
--                             page, members download only. public: on the map
--                             with the community badge, but download requires an
--                             active membership (402 membership_required).
--   A tour with community_id NULL has community_visibility NULL and behaves
--   exactly as before — the columns are inert for every existing row.

BEGIN;

-- ─── D663 §2 — who may charge ────────────────────────────────────────────────
-- l4 is already TRUE (migration 012). l1 stays FALSE. This asserts l2/l3/tester.
UPDATE plans SET can_sell = TRUE WHERE plan_id IN ('l2', 'l3', 'tester');

-- ─── D663 §3 — community tour columns on audio_tours ─────────────────────────
ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS community_id INTEGER;

ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS community_visibility VARCHAR(16)
    CHECK (community_visibility IS NULL
           OR community_visibility IN ('members', 'public'));

-- FK to communities. Added separately + guarded so this migration is safe on a
-- DB where 029_communities has not run yet (the column still exists; the FK is
-- simply skipped) and is not duplicated on a re-run.
DO $$
BEGIN
    IF to_regclass('communities') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'fk_audio_tours_community'
             AND conrelid = 'audio_tours'::regclass
       ) THEN
        ALTER TABLE audio_tours
            ADD CONSTRAINT fk_audio_tours_community
            FOREIGN KEY (community_id) REFERENCES communities(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- A partial index for the two hot reads: "the tours of community N" (the
-- community page) and "the public community tours on the map".
CREATE INDEX IF NOT EXISTS idx_audio_tours_community
    ON audio_tours (community_id) WHERE community_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audio_tours_community_public
    ON audio_tours (community_id)
    WHERE community_id IS NOT NULL AND community_visibility = 'public';

COMMENT ON COLUMN audio_tours.community_id IS
    'LOCAL-701/D663 §3: the community this tour was generated FOR (NULL = an '
    'ordinary public tour). The organiser was charged from their plan allowance.';
COMMENT ON COLUMN audio_tours.community_visibility IS
    'LOCAL-701/D663 §3: members (default — community page only, members download) '
    'or public (on the map with the community badge; download needs a membership).';

COMMIT;
