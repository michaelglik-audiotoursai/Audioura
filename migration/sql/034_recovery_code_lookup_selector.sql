-- 034_recovery_code_lookup_selector.sql  (LOCAL-695B — bounce of LOCAL-695)
--
-- DEFECT (LEAD review 2026-10-14): recovery_code_service._match_code SELECTed
-- EVERY row of recovery_codes and ran PBKDF2-HMAC-SHA256 (200k iterations)
-- against each one to find the matching profile. That is O(N) PBKDF2 per
-- restore: at 1,000 profiles a single restore takes ~100 s, and because the
-- per-device rate limit does not help across devices, anyone can tie up the
-- orchestrator by submitting codes. A restore must be O(1).
--
-- FIX (selector / "lookup" column): alongside the slow verifier hash, store a
-- fast, deterministic SELECTOR:
--
--     code_lookup = HMAC-SHA256(RECOVERY_CODE_PEPPER, normalized_code)   (hex)
--
--   * It is keyed by a server-held pepper (env RECOVERY_CODE_PEPPER, 32+ random
--     bytes) that is NOT in the database, so holding the DB still does not let an
--     attacker precompute lookups for guessed codes — the pepper is required.
--   * It is deterministic (no per-row salt), so a restore computes it ONCE and
--     fetches EXACTLY ONE row via the UNIQUE index below, then verifies that one
--     row with the existing per-code-salted PBKDF2 hash in constant time. One
--     PBKDF2 per restore instead of N.
--   * It is NOT the verifier: the PBKDF2 code_hash + code_salt stay the stored
--     secret of record. code_lookup only narrows the search to one row.
--
-- WHAT THIS ADDS, PURELY ADDITIVELY (no DROP, no DELETE, no type change):
--
--   1. recovery_codes.code_lookup VARCHAR(64) — hex HMAC-SHA256 selector,
--      NULLable so the column can be added to a populated table without a
--      backfill (existing TEST-only rows get it on their next rotate).
--
--   2. a UNIQUE index on code_lookup (partial: WHERE code_lookup IS NOT NULL),
--      so the restore lookup is a single indexed row fetch and two profiles can
--      never share a selector. Partial so legacy rows that predate the column
--      (NULL) do not collide on NULL.
--
-- Idempotent & safe to re-run: ADD COLUMN IF NOT EXISTS and CREATE UNIQUE INDEX
-- IF NOT EXISTS only. recovery_code_service.ensure_recovery_schema() self-heals
-- to the SAME shape, so the feature works whether or not this file was run.

BEGIN;

ALTER TABLE recovery_codes
    ADD COLUMN IF NOT EXISTS code_lookup VARCHAR(64);

COMMENT ON COLUMN recovery_codes.code_lookup IS
    'LOCAL-695B: hex HMAC-SHA256(RECOVERY_CODE_PEPPER, normalized_code) — a fast '
    'deterministic SELECTOR that makes restore an O(1) single-row lookup instead '
    'of scanning every PBKDF2 hash. The pepper lives in env (not the DB); the '
    'PBKDF2 code_hash + code_salt remain the verifier. NULL on legacy rows until '
    'their next generate/rotate.';

-- Partial UNIQUE index: one profile per selector; NULL legacy rows excluded.
CREATE UNIQUE INDEX IF NOT EXISTS uq_recovery_codes_lookup
    ON recovery_codes (code_lookup)
    WHERE code_lookup IS NOT NULL;

COMMIT;
