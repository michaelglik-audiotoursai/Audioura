-- 033_recovery_code_portability.sql  (LOCAL-695, D660 addendum / D660 §3 of
--  OWNER_DECISIONS_privacy_and_profile_portability_2026_06_11.md)
--
-- "A lost phone is not a deletion — the listener should get their Listen page
--  back." (Michael, June 2026). The user id is derived from device hardware, so
--  a replaced/lost phone = a new id = an empty Listen page, and under D660 a
--  paid tour would otherwise have to be bought again. This migration adds the
--  server side of an ANONYMOUS RECOVERY CODE: a portable secret the listener
--  holds (never an email/password — anonymity is preserved, D-privacy). On a
--  new phone, entering the code links that device to the profile (via the
--  existing user_consolidation_map / device_consolidation_history), unlinks the
--  old device (one profile lives on one phone at a time), and re-grants the
--  paid tours the profile owned so they re-download WITHOUT paying again.
--
-- The recovery code itself is NEVER stored in plaintext — only a salted hash
-- (PBKDF2-HMAC-SHA256). Holding the database does not reveal any code. This
-- mirrors the "stored hashed" promise in the privacy draft.
--
-- WHAT THIS ADDS, PURELY ADDITIVELY (no DROP, no DELETE, no column type change):
--
--   1. recovery_codes — ONE row per profile (consolidated_user_id), carrying
--      the PBKDF2 hash + per-code salt + parameters, when it was generated, and
--      when it was last rotated. The code is offered once, proactively, right
--      after the listener's FIRST purchase; a profile has at most one ACTIVE
--      code (re-generating rotates it in place). consolidated_user_id is the
--      profile key, matching user_consolidation_map.
--
--   2. profile_restores — an append-only LOG of every successful restore: which
--      profile, the NEW device that claimed it, the device it UNLINKED, how many
--      paid-tour restore grants were issued, and when. This is the audit trail
--      and the source for the ">2 restores in 30 days → refuse with Contact
--      support" abuse guard (D654): the guard counts rows here in the window.
--
--   3. restore_attempts — an append-only LOG of every restore ATTEMPT (success
--      or failure) keyed by the requesting device id, for the per-device rate
--      limit (default 5 attempts / hour / device). Separate from
--      profile_restores because a wrong code never reaches a profile but must
--      still count against the device's rate budget.
--
--   4. device_consolidation_history.unlinked_at TIMESTAMPTZ — when a device was
--      UNLINKED from the profile by a later restore (the old phone moved away).
--      NULL = still linked. The map_delivery "profile moved" abuse guard reads
--      this: a device whose most-recent history row is unlinked no longer gets
--      re-download grants (tours already on it keep playing — D654). Added here
--      (not a new table) because the row already models device↔profile linkage.
--
--   5. tour_unlocks already carries store='restore' rows as the RESTORE GRANT
--      (an unconsumed unlock the download gate honours, consumed once on the
--      re-download — one per tour per restore). No new column is needed; the
--      restore endpoint INSERTs an unconsumed tour_unlocks row per owned paid
--      tour, exactly like a purchase, tagged store='restore', transaction_id =
--      'restore:<profile>:<ts>' for the audit trail.
--
-- Idempotent & safe to re-run: CREATE TABLE / INDEX IF NOT EXISTS and ADD COLUMN
-- IF NOT EXISTS only. The recovery/restore route module (recovery_code_service.py)
-- and the map_delivery gate self-heal to the SAME shape via _ensure_* DDL, so the
-- feature works whether or not this file was ever run on a given DB.

BEGIN;

-- ─── 1. recovery_codes — one active code per profile, stored hashed ──────────
CREATE TABLE IF NOT EXISTS recovery_codes (
    consolidated_user_id VARCHAR(255) PRIMARY KEY,  -- the profile (user_consolidation_map key)
    code_hash            BYTEA        NOT NULL,      -- PBKDF2-HMAC-SHA256(code, salt, iterations)
    code_salt            BYTEA        NOT NULL,      -- per-code random salt (>=16 bytes)
    hash_algo            VARCHAR(32)  NOT NULL DEFAULT 'pbkdf2_sha256',
    hash_iterations      INTEGER      NOT NULL DEFAULT 200000,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    rotated_at           TIMESTAMPTZ                  -- last re-generation; NULL = never rotated
);

COMMENT ON TABLE recovery_codes IS
    'LOCAL-695: one anonymous recovery code per profile (consolidated_user_id), '
    'stored ONLY as a salted PBKDF2-HMAC-SHA256 hash — never plaintext. Offered '
    'once after the first purchase; entering it on a new phone restores the '
    'Listen page. Re-generating rotates the hash in place.';
COMMENT ON COLUMN recovery_codes.code_hash IS
    'PBKDF2-HMAC-SHA256 of the recovery code with code_salt and hash_iterations. '
    'The database alone never reveals the code.';

-- ─── 2. profile_restores — audit log + source for the >2/30d abuse guard ─────
CREATE TABLE IF NOT EXISTS profile_restores (
    id                   SERIAL PRIMARY KEY,
    consolidated_user_id VARCHAR(255) NOT NULL,      -- the profile that was restored
    new_device_id        VARCHAR(255) NOT NULL,      -- the phone that claimed it
    unlinked_device_id   VARCHAR(255),               -- the phone it moved away from (NULL if none)
    grants_issued        INTEGER      NOT NULL DEFAULT 0,  -- paid-tour restore grants written
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profile_restores_profile_time
    ON profile_restores (consolidated_user_id, created_at);

COMMENT ON TABLE profile_restores IS
    'LOCAL-695: append-only log of each successful profile restore (recovery '
    'code accepted). The abuse guard refuses a restore when a profile has more '
    'than 2 rows here in the last 30 days (→ "Contact support", D654).';

-- ─── 3. restore_attempts — per-device rate-limit ledger (5/hour/device) ──────
CREATE TABLE IF NOT EXISTS restore_attempts (
    id            SERIAL PRIMARY KEY,
    device_id     VARCHAR(255) NOT NULL,             -- the requesting (new) device
    outcome       VARCHAR(32)  NOT NULL,             -- 'success' | 'bad_code' | 'rate_limited' | 'refused_abuse' | 'error'
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_restore_attempts_device_time
    ON restore_attempts (device_id, created_at);

COMMENT ON TABLE restore_attempts IS
    'LOCAL-695: append-only log of every restore ATTEMPT (success or failure) '
    'keyed by requesting device, for the per-device rate limit (default '
    '5 attempts / hour / device). A wrong code counts here even though it never '
    'touches a profile.';

-- ─── 4. device_consolidation_history.unlinked_at — the "profile moved" flag ──
ALTER TABLE device_consolidation_history
    ADD COLUMN IF NOT EXISTS unlinked_at TIMESTAMPTZ;

COMMENT ON COLUMN device_consolidation_history.unlinked_at IS
    'LOCAL-695: when this device was UNLINKED from the profile by a later '
    'restore (the old phone moved away). NULL = still linked. The map_delivery '
    'abuse guard refuses re-download grants to a device whose latest history row '
    'is unlinked; tours already on that phone keep playing (D654).';

COMMIT;
