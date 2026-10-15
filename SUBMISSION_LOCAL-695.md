# SUBMISSION — LOCAL-695: Restore my Listen page (anonymous recovery code)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-695-recovery-code` (from `subscribed`, base `43edbcca`)
**Design:** `OWNER_DECISIONS_privacy_and_profile_portability_2026_06_11.md` §3 (D660 addendum)

## Problem
The user id is derived from device hardware, so a lost/replaced phone = a new id =
an empty Listen page, and under D660 a paid tour would have to be bought again.
Michael: a lost phone is not a deletion — the listener should get their Listen page
back (paid tours without paying again, free tours, news articles).

## What was built

### 1. Anonymous recovery code (server-side)
`recovery_code_service.py` (new, repo root), registered on the orchestrator via
`register_recovery_routes(app)` (defensive import, same pattern as pricing/ratings).
- **Code:** 4×4 Crockford-base32 characters (ambiguous I/L/O/U excluded), 80 bits of
  entropy from `secrets`. Shown to the listener **once**.
- **Storage:** only a salted **PBKDF2-HMAC-SHA256** hash (200k iterations) + per-code
  salt. The plaintext is never stored; the database alone never reveals a code.
- **Endpoints:**
  - `POST /recovery-code/generate {user_id}` → `{code, created_at}` (201). Re-generating
    **rotates** the code (old one stops working). Offered once after the first purchase
    (client flag `recovery_code_offered`), always available from About.
  - `GET  /recovery-code/status?user_id=…` → `{has_code, created_at, rotated_at}`.
  - `POST /recovery-code/restore {user_id, code}` → `{restored, listen_page, …}`
    (200 / 401 bad code / 429 rate-limited / 409 refused).

### 2. Restore
On a new phone, a valid code:
1. **Links** the new device to the profile and **unlinks** the previous device(s) —
   one profile lives on one phone at a time (`user_consolidation_map`,
   `device_consolidation_history.unlinked_at`).
2. Issues a **restore grant** per owned paid tour: an **unconsumed `tour_unlocks`
   row tagged `store='restore'`** that the existing download gate honours and consumes
   once (one grant per tour per restore) — paid tours re-download **without paying
   again**.
3. Returns the **Listen-page list** (free tours, paid tours, news articles) for the app
   to re-download.

### 3. Abuse guards
- **Per-device rate limit:** default **5 attempts / hour / device** (`restore_attempts`
  ledger); the 6th attempt is `429` before the code is even checked.
- **>2 restores / 30 days** for a profile → `409` "Contact support" (`profile_restores`).
- **Moved-away old phone** (`map_delivery/app.py` `_device_moved_away` + gate): a device
  unlinked by a later restore is refused re-downloads of paid rows (`402 profile_moved`);
  **tours already on it keep playing** (local/offline, D654) and anything it downloaded
  while free still downloads.

### 4. Consolidation-aware deletion
`DELETE /delete-account/<secret_id>` (orchestrator) now resolves the **consolidated
identity across ALL linked devices** (`recovery_code_service.linked_device_ids_for_deletion`)
and deletes device-keyed rows for every linked device plus the profile id, including the
recovery code and restore ledgers. Single-device users resolve to a one-element set, so
the previous behaviour is unchanged.

### 5. Flutter UI (`audio_tour_app/`)
- `lib/utils/recovery_code.dart` — pure helpers (normalize/validate/format) mirroring the
  server's normalization.
- `lib/screens/recovery_code_screen.dart` — two sections: **Your recovery code** (Create,
  Copy, New code, one-line explanation) and **Restore my Listen page** (enter code →
  restore, with 401/429/409 messaging). `maybeOfferRecoveryCode()` offers it once after the
  first purchase.
- `lib/screens/about_screen.dart` — new "Recovery code" section linking to the screen.

### 6. Privacy draft
`legal/PRIVACY.md` → version `2026-10-14-draft4`: a "What changed" bullet, a dedicated
**Recovery code** subsection (anonymous, stored hashed, one phone at a time, rate-limited
and logged, lost-code-is-unrecoverable), a retention note, and a consolidated-identity
deletion note. HTML regenerated with `python3 legal/build_html.py` (the `legal/html/`
artifacts are git-ignored). App build bumped `2.4.17+52 → 2.4.18+53`.

## Migration
`migration/sql/033_recovery_code_portability.sql` — **additive only** (next free number):
`recovery_codes`, `profile_restores`, `restore_attempts`, and
`device_consolidation_history.unlinked_at`. Restore grants reuse `tour_unlocks`
(`store='restore'`) — no new column. Idempotent (`CREATE … IF NOT EXISTS`, `ADD COLUMN
IF NOT EXISTS`); the service self-heals the same shape, so re-running the file is a clean
no-op.

## Tests
- `tests/test_local695_recovery_code.py` — **12 pass** (`audiotours_test`): code
  shape/alphabet, 1000-unique entropy, hash-not-plaintext + constant-time verify +
  rotation, restore links/unlinks + grant issued, paid re-download free on the new device
  only (a stranger still gets 402), moved-away old device 402 `profile_moved` (grandfathered
  free still works), rate-limit 6th=429, >2/30d=409, unknown code=401, consolidated
  deletion spans the profile and removes all linked rows.
- `audio_tour_app/test/recovery_code_test.dart` — **11 pass** (`flutter test`): helper
  normalization/validation/formatting + widget renders both sections, Restore rejects an
  incomplete code without a network call, and the offer banner shows.
- Adjacent paid-tour suites (`test_local693_paid_per_download.py`,
  `test_local677_paid_tours.py`) — **34 pass**: the gate change did not regress the paywall.
- `flutter analyze` on the three new Dart files: **no issues**.

## Row counts (before / after)
`audiotours_test`, measured around the full test run:

| table | before | after |
|---|---|---|
| recovery_codes | 0 | 0 |
| profile_restores | 0 | 0 |
| restore_attempts | 0 | 0 |
| device_consolidation_history | 0 | 0 |
| user_consolidation_map | 0 | 0 |
| tour_unlocks | 0 | 0 |
| tour_downloads | 125 | 125 |

The suite self-heals the 033 schema, writes only `TEST-695-` / `CONSOLIDATED-TEST-695-`
rows, and cleans them up; the shared `tour_downloads` baseline (125) is untouched.

## Process
Additive migration (next free number 033), own-containers + `is_test`/`TEST-695-` data
only, no `-p audioura`, no `audioura-*` renames. No edits to
DECISIONS/CLAUDE/BACKLOG/WORK_QUEUE/.continuous_dev.

---

# 695B — Recovery code lookup must be O(1), not a scan of every stored hash

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-695-recovery-code` (CONTINUE; merged `origin/subscribed` first, base now `405322a4`)
**Bounce of:** LOCAL-695 — LEAD review 2026-10-14

## Defect (LEAD)
`recovery_code_service._match_code` `SELECT`ed **every** row of `recovery_codes` and ran
PBKDF2-HMAC-SHA256 (200k iterations) against each one to find the matching profile. That is
**O(N) PBKDF2 per restore**: at 1,000 profiles a single restore takes ~100 s, and because the
per-device rate limit does not help *across* devices, anyone can tie up the orchestrator by
submitting codes. A restore must be O(1).

## Fix — HMAC selector ("lookup") column
Alongside the slow verifier hash, store a fast deterministic **selector**:

```
code_lookup = HMAC-SHA256(RECOVERY_CODE_PEPPER, normalized_code)   (lowercase hex)
```

- **Written at generate/rotate** (`generate_for_device`) into the new `recovery_codes.code_lookup`
  column, which carries a **partial UNIQUE index** (`uq_recovery_codes_lookup … WHERE code_lookup
  IS NOT NULL`). Rotation overwrites it (`ON CONFLICT … DO UPDATE SET code_lookup = EXCLUDED…`),
  so the old code's selector resolves to nothing.
- **Restore** (`_match_code`) computes the selector **once**, fetches **exactly one row** by the
  unique index, then verifies that single row with the existing per-code-salted PBKDF2 hash in
  constant time (`hmac.compare_digest`). **One PBKDF2 per restore instead of N.**
- The selector is **not** the verifier — `code_hash` + `code_salt` (PBKDF2) remain the stored
  secret of record. `code_lookup` only narrows the search to one row.

## Pepper (why holding the DB is still safe)
The selector is keyed by a server-held pepper from env **`RECOVERY_CODE_PEPPER`** (32+ random
bytes) that is **never stored in the database**. Without it, an attacker holding a DB dump cannot
precompute selectors for guessed codes. Because the pepper is mandatory:

- If `RECOVERY_CODE_PEPPER` is **missing/blank**, `register_recovery_routes` logs a clear
  `logger.error("RECOVERY_CODE_PEPPER is not set — recovery-code routes are DISABLED …")` line and
  mounts a **503 stub** for every `/recovery-code/*` path. It **never** falls back to the O(N)
  scan. The core ops (`compute_lookup`, `generate_for_device`, `_match_code`) raise
  `PepperMissingError` rather than scanning.

> **LEAD action required:** add `RECOVERY_CODE_PEPPER=<32+ random bytes>` to `~/Audioura/.env`
> (e.g. `python3 -c "import secrets;print(secrets.token_hex(32))"`). The compose file references
> it as `${RECOVERY_CODE_PEPPER}` for the orchestrator; **I did not write `.env` myself.**

## Changes
- **`migration/sql/034_recovery_code_lookup_selector.sql`** (new, next free number, additive):
  `ADD COLUMN IF NOT EXISTS code_lookup VARCHAR(64)` + `CREATE UNIQUE INDEX IF NOT EXISTS
  uq_recovery_codes_lookup … WHERE code_lookup IS NOT NULL`. Idempotent; no DROP/DELETE/type-change.
  Existing rows (test only) are rotated to populate the column.
- **`recovery_code_service.py`**: `get_pepper()`, `PepperMissingError`, `compute_lookup()`;
  `generate_for_device` writes `code_lookup`; `_match_code` is now a single indexed fetch + one
  PBKDF2 verify; `ensure_recovery_schema` self-heals the column + index (mirrors 034);
  `register_recovery_routes` refuses (503 + log) when the pepper is absent.
- **`docker-compose.subscribed-local.yml`**: `RECOVERY_CODE_PEPPER=${RECOVERY_CODE_PEPPER}` on the
  `tour-orchestrator` service.
- **`tests/test_local695_recovery_code.py`**: loader sets a deterministic test pepper; five new
  695B tests added.

## Tests (all pass against `audiotours_test`)
- **5,000 synthetic codes stored → restore in < 0.5 s** (`test_restore_with_5000_codes_under_half_second`;
  decoys seeded cheaply, target gets a real hash + lookup; measured well under the 0.5 s bar).
- **Wrong code → one query** (`test_match_code_is_single_query`): a `_CountingCursor` proves both a
  hit and a miss read `recovery_codes` **exactly once**, regardless of how many codes are stored.
- **Rotation updates the lookup** (`test_generate_writes_lookup_and_rotation_updates_it`): the new
  code's selector replaces the old one; the old selector resolves to zero rows; `_match_code`
  accepts the new code and rejects the old.
- **Missing pepper → routes disabled + ops refuse** (`test_missing_pepper_disables_routes_and_refuses_ops`):
  `/recovery-code/*` returns 503 (`recovery_disabled`); `compute_lookup`/`generate_for_device` raise
  `PepperMissingError` — never a scan.
- **Selector shape** (`test_lookup_is_hex_hmac_and_pepper_dependent`): 64-hex, deterministic,
  format/case-insensitive, and changes with the pepper.
- Full recovery suite: **17 passed**. Combined bar `-k "677 or 690 or 691 or 693 or 695"`:
  **90 passed, 0 failed**.
- Migration 034 validated via `psycopg2`: applies twice (idempotent); `code_lookup` is
  `character varying`; `uq_recovery_codes_lookup` is the partial unique btree index.

## Process
Merged `origin/subscribed` first (`git merge-base --is-ancestor 405322a4 HEAD` → 0). Additive
migration (034), own-containers + `TEST-695-` / `CONSOLIDATED-TEST-695-` data only, no `-p audioura`,
no `audioura-*` renames. No edits to DECISIONS/CLAUDE/BACKLOG/WORK_QUEUE/.continuous_dev. Did **not**
write `.env` (pepper is LEAD's to add).
