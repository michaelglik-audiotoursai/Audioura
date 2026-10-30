-- 03_local821_seed.sql — LOCAL-821 live-proof seed (runs after schema + plans).
--
-- A single test device on the 'l3' pack (fresh_per_pack=5, max_stops=10,
-- by_reference_only=FALSE → FRESH generation) so the orchestrator's quota check
-- allows the one short walking tour this proof generates. This is this stack's
-- OWN postgres volume (project local821), invisible to the shared dev DB and
-- dropped with `down -v`. No real tour is pre-seeded: the proof generates one
-- fresh, kills the orchestrator mid-generation, and a fresh orchestrator
-- resumes and stores it.

INSERT INTO users (secret_id, plan) VALUES ('local821-tester', 'l3')
    ON CONFLICT (secret_id) DO NOTHING;

INSERT INTO device_entitlement (user_id, level) VALUES ('local821-tester', 'l3')
    ON CONFLICT (user_id) DO UPDATE SET level = 'l3';
