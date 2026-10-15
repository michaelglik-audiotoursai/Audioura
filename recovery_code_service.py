#!/usr/bin/env python3
"""
recovery_code_service.py — LOCAL-695 anonymous recovery code / profile portability
==================================================================================

"A lost phone is not a deletion — the listener should get their Listen page back"
(Michael, June 2026; OWNER_DECISIONS_privacy_and_profile_portability_2026_06_11.md
§3). The user id is derived from device hardware, so a replaced/lost phone = a new
id = an empty Listen page, and under D660 a paid tour would otherwise have to be
bought again. This module is the SERVER side of an anonymous RECOVERY CODE.

WHAT A RECOVERY CODE IS
-----------------------
A portable, high-entropy secret the listener holds — NOT an email/password, so
anonymity is preserved (even the owner can't map it to a person). The code is
offered once, proactively, right after the listener's FIRST purchase. It is shown
exactly once (the server returns the plaintext only at generation time) and is
stored ONLY as a salted PBKDF2-HMAC-SHA256 hash. Holding the database never
reveals the code.

Default format: 4 groups of 4 Crockford-base32 characters (e.g. ABCD-EFGH-JKLM-
NPQR) = 16 symbols × 5 bits = 80 bits of entropy. Ambiguous characters (I, L, O,
U) are excluded so a human can copy it reliably.

RESTORE
-------
On a new phone, entering the code:
  1. validates the code against every stored hash (equality via the per-code salt);
  2. LINKS the new device id to the profile (user_consolidation_map /
     device_consolidation_history), and UNLINKS the previous device — one profile
     lives on one phone at a time;
  3. issues a RESTORE GRANT for each PAID tour the profile owned: an unconsumed
     tour_unlocks row (store='restore') the download gate already honours, spent
     once on the re-download (one grant per tour per restore);
  4. returns the Listen-page list (free tours, paid tours, news articles) for the
     app to re-download.

ABUSE GUARDS
------------
  * Per-device RATE LIMIT: default 5 attempts / hour / device (restore_attempts).
  * >2 successful restores for a profile in 30 days → refuse with
    "Contact support" (profile_restores). (D654.)
  * The UNLINKED old device: map_delivery reads device_consolidation_history.
    unlinked_at and stops offering re-download grants to a moved-away device;
    tours already on it keep playing (D654). (Enforced in map_delivery/app.py.)

HOSTING
-------
Registered on the orchestrator (port 5002) via register_recovery_routes(app), the
same defensive pattern as pricing/ratings/reviews. The orchestrator already hosts
account deletion and can import the repo-root consolidation module. All reads/
writes are against the same postgres-2 DB.

Endpoints (JSON):
  POST /recovery-code/generate   {user_id}  -> {code, created_at}         (201)
        - Offered after the first purchase. Idempotent-ish: regenerating ROTATES
          the code (old code stops working). Requires the profile to exist (a
          consolidated_user_id is created from the device id if absent).
  GET  /recovery-code/status?user_id=...     -> {has_code, created_at, ...}
  POST /recovery-code/restore    {user_id, code} -> {restored, listen_page, ...}
        - 200 restored, 400 bad input, 401 bad code, 429 rate limited,
          409 refused_abuse (Contact support).

Self-heals its schema (mirrors migration 033) so it works whether or not the
migration file has been run.
"""

import os
import hmac
import hashlib
import secrets
import logging
from datetime import datetime

import psycopg2
from flask import request, jsonify

logger = logging.getLogger("recovery_code_service")

# ─── tunables (env-overridable, with the ticket's defaults) ───────────────────
RESTORE_RATE_LIMIT_PER_HOUR = int(os.getenv("RESTORE_RATE_LIMIT_PER_HOUR", "5"))
RESTORE_MAX_PER_30_DAYS = int(os.getenv("RESTORE_MAX_PER_30_DAYS", "2"))
PBKDF2_ITERATIONS = int(os.getenv("RECOVERY_CODE_ITERATIONS", "200000"))

# Crockford base32 without the ambiguous I, L, O, U — easy to read and copy.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_GROUPS = 4
_GROUP_LEN = 4


# ──────────────────────────────────────────────────────────────────────────────
# Pure helpers (no DB) — unit-testable in isolation
# ──────────────────────────────────────────────────────────────────────────────

def generate_recovery_code():
    """Return a fresh, high-entropy recovery code string.

    Format: 4 groups of 4 characters from a 32-symbol alphabet, hyphen-joined
    (e.g. 'ABCD-EFGH-JKLM-NPQR'). 16 symbols × 5 bits = 80 bits of entropy, drawn
    from secrets.choice (a CSPRNG). Ambiguous characters (I, L, O, U) are
    excluded so a human can transcribe it without error."""
    chars = [secrets.choice(_ALPHABET) for _ in range(_GROUPS * _GROUP_LEN)]
    groups = [
        "".join(chars[i * _GROUP_LEN:(i + 1) * _GROUP_LEN]) for i in range(_GROUPS)
    ]
    return "-".join(groups)


def normalize_code(code):
    """Canonicalise a user-entered code for comparison: strip spaces/hyphens,
    uppercase, and map visually ambiguous characters to the canonical alphabet
    (I/L→1, O→0, U→V). Returns '' for falsy input. The stored hash is always
    computed over this normalized form, so 'abcd efgh...' and 'ABCD-EFGH-...'
    match the same code."""
    if not code:
        return ""
    s = str(code).strip().upper()
    s = s.replace("-", "").replace(" ", "")
    trans = str.maketrans({"I": "1", "L": "1", "O": "0", "U": "V"})
    return s.translate(trans)


def hash_code(code, salt, iterations=PBKDF2_ITERATIONS):
    """PBKDF2-HMAC-SHA256 of the NORMALIZED code with the given salt. Returns the
    raw digest bytes. Deterministic for a (code, salt, iterations) triple."""
    norm = normalize_code(code).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", norm, salt, int(iterations))


def verify_code(code, salt, expected_hash, iterations=PBKDF2_ITERATIONS):
    """Constant-time check that `code` hashes (with `salt`, `iterations`) to
    `expected_hash`. Uses hmac.compare_digest to avoid timing leaks."""
    if not code or salt is None or expected_hash is None:
        return False
    candidate = hash_code(code, salt, iterations)
    return hmac.compare_digest(candidate, bytes(expected_hash))


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_conn():
    """Open a connection to the shared postgres DB. Honours the standard env
    vars the orchestrator uses (DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT);
    defaults match the orchestrator's deletion endpoint (postgres-2:5432)."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres-2"),
        database=os.getenv("DB_NAME", "audiotours"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "password123"),
        port=os.getenv("DB_PORT", "5432"),
    )


_SCHEMA_READY = False


def ensure_recovery_schema(cur):
    """Self-healing DDL mirroring migration 033. Idempotent; cached so it runs at
    most once per process. Does NOT commit (the caller owns the transaction).
    Creates recovery_codes, profile_restores, restore_attempts, and adds
    device_consolidation_history.unlinked_at. Also ensures the consolidation
    tables themselves exist (phase3 migration) so a fresh DB works."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    # Consolidation tables (phase3) — create if a bare DB lacks them.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_consolidation_map (
            consolidated_user_id VARCHAR(255) PRIMARY KEY,
            primary_device_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            last_merged_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS device_consolidation_history (
            id SERIAL PRIMARY KEY,
            consolidated_user_id VARCHAR(255) NOT NULL,
            merged_device_id VARCHAR(255) NOT NULL,
            domain VARCHAR(255) NOT NULL,
            merged_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS recovery_codes (
            consolidated_user_id VARCHAR(255) PRIMARY KEY,
            code_hash       BYTEA        NOT NULL,
            code_salt       BYTEA        NOT NULL,
            hash_algo       VARCHAR(32)  NOT NULL DEFAULT 'pbkdf2_sha256',
            hash_iterations INTEGER      NOT NULL DEFAULT 200000,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            rotated_at      TIMESTAMPTZ
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS profile_restores (
            id SERIAL PRIMARY KEY,
            consolidated_user_id VARCHAR(255) NOT NULL,
            new_device_id        VARCHAR(255) NOT NULL,
            unlinked_device_id   VARCHAR(255),
            grants_issued        INTEGER NOT NULL DEFAULT 0,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_profile_restores_profile_time "
        "ON profile_restores (consolidated_user_id, created_at)"
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS restore_attempts (
            id SERIAL PRIMARY KEY,
            device_id  VARCHAR(255) NOT NULL,
            outcome    VARCHAR(32)  NOT NULL,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_restore_attempts_device_time "
        "ON restore_attempts (device_id, created_at)"
    )
    cur.execute(
        "ALTER TABLE device_consolidation_history "
        "ADD COLUMN IF NOT EXISTS unlinked_at TIMESTAMPTZ"
    )
    _SCHEMA_READY = True


def _resolve_profile_id(cur, device_id):
    """The consolidated_user_id for a device id, or None if the device is not yet
    part of any profile.

    A device is linked to a profile if either:
      * it is the primary_device_id of a user_consolidation_map row, OR
      * it has a device_consolidation_history row that is still linked
        (unlinked_at IS NULL).
    Returns the most relevant profile id, or None."""
    # Primary device of a profile.
    cur.execute(
        "SELECT consolidated_user_id FROM user_consolidation_map "
        "WHERE primary_device_id = %s ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    # A still-linked merged device.
    cur.execute(
        "SELECT consolidated_user_id FROM device_consolidation_history "
        "WHERE merged_device_id = %s AND unlinked_at IS NULL "
        "ORDER BY merged_at DESC LIMIT 1",
        (device_id,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    return None


def _get_or_create_profile_id(cur, device_id):
    """Return the device's profile id, creating a new consolidated_user_id (and
    mapping this device as its primary) if the device has none yet. This lets a
    listener generate a recovery code even if they have never consolidated — the
    profile is simply this one device until a restore links another."""
    existing = _resolve_profile_id(cur, device_id)
    if existing:
        return existing
    consolidated_user_id = f"CONSOLIDATED-{device_id}-{int(datetime.now().timestamp())}"
    cur.execute(
        "INSERT INTO user_consolidation_map (consolidated_user_id, primary_device_id) "
        "VALUES (%s, %s) ON CONFLICT (consolidated_user_id) DO NOTHING",
        (consolidated_user_id, device_id),
    )
    return consolidated_user_id


def _linked_device_ids(cur, profile_id):
    """Every device id currently linked to a profile: the primary device plus
    every still-linked merged device (unlinked_at IS NULL). Used by restore (to
    unlink the old one) and by consolidation-aware deletion."""
    ids = set()
    cur.execute(
        "SELECT primary_device_id FROM user_consolidation_map "
        "WHERE consolidated_user_id = %s",
        (profile_id,),
    )
    for r in cur.fetchall():
        if r[0]:
            ids.add(r[0])
    cur.execute(
        "SELECT merged_device_id FROM device_consolidation_history "
        "WHERE consolidated_user_id = %s AND unlinked_at IS NULL",
        (profile_id,),
    )
    for r in cur.fetchall():
        if r[0]:
            ids.add(r[0])
    return ids


# ──────────────────────────────────────────────────────────────────────────────
# Listen-page list + restore grants
# ──────────────────────────────────────────────────────────────────────────────

def _owned_paid_tour_ids(cur, device_ids):
    """ORIGINAL tour ids the profile PAID for across all its device ids: every
    tour_unlocks row (consumed or not) whose store is NOT 'restore'. A previous
    restore grant (store='restore') is excluded so restores never compound.
    Returns a set of ints."""
    if not device_ids:
        return set()
    cur.execute(
        "SELECT DISTINCT tour_id FROM tour_unlocks "
        "WHERE user_id = ANY(%s) AND (store IS DISTINCT FROM 'restore')",
        (list(device_ids),),
    )
    return {int(r[0]) for r in cur.fetchall() if r[0] is not None}


def _downloaded_tour_ids(cur, device_ids):
    """Tour ids the profile had DOWNLOADED across its devices (free or paid),
    split into free vs paid by was_free. Returns (free_ids, paid_ids)."""
    free_ids, paid_ids = set(), set()
    if not device_ids:
        return free_ids, paid_ids
    try:
        cur.execute(
            "SELECT tour_id, was_free FROM tour_downloads WHERE user_id = ANY(%s)",
            (list(device_ids),),
        )
        for tid, was_free in cur.fetchall():
            if tid is None:
                continue
            (free_ids if was_free else paid_ids).add(int(tid))
    except Exception:  # noqa: BLE001 — pre-023 DB: no downloads ledger
        pass
    return free_ids, paid_ids


def _news_article_ids(cur, device_ids):
    """News article ids the profile requested across its devices (the Listen
    page's news section). Best-effort — returns [] if the table is absent."""
    if not device_ids:
        return []
    try:
        cur.execute(
            "SELECT DISTINCT article_id FROM article_requests "
            "WHERE secret_id = ANY(%s) AND article_id IS NOT NULL",
            (list(device_ids),),
        )
        return [r[0] for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def _issue_restore_grants(cur, profile_id, new_device_id, paid_tour_ids):
    """For each paid tour the profile owned, write ONE unconsumed tour_unlocks
    row for the NEW device, tagged store='restore' — a RESTORE GRANT the
    download gate honours and consumes once on the re-download (one grant per
    tour per restore). Idempotent against the partial active-unlock index: if the
    new device already holds an active unlock for a tour, ON CONFLICT DO NOTHING
    keeps a single grant. Returns the number of grants written."""
    if not paid_tour_ids:
        return 0
    # Ensure the consumption columns + partial unique index exist (mirrors 031),
    # so the ON CONFLICT target is valid on a pre-031 DB.
    try:
        cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_by_download_id VARCHAR(255)")
        cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS restored_at TIMESTAMPTZ")
        cur.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname='uq_tour_unlocks_user_tour' AND conrelid='tour_unlocks'::regclass) "
            "THEN ALTER TABLE tour_unlocks DROP CONSTRAINT uq_tour_unlocks_user_tour; END IF; END $$;"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tour_unlocks_active "
            "ON tour_unlocks (user_id, tour_id) WHERE consumed_at IS NULL"
        )
    except Exception:  # noqa: BLE001
        pass
    txn = f"restore:{profile_id}:{int(datetime.now().timestamp())}"
    issued = 0
    for tid in sorted(paid_tour_ids):
        try:
            cur.execute(
                "INSERT INTO tour_unlocks (user_id, tour_id, transaction_id, store, price_usd) "
                "VALUES (%s, %s, %s, 'restore', 0) "
                "ON CONFLICT (user_id, tour_id) WHERE consumed_at IS NULL DO NOTHING",
                (new_device_id, int(tid), txn),
            )
            if cur.rowcount and cur.rowcount > 0:
                issued += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("restore grant insert failed for tour %s: %s", tid, e)
    return issued


def build_listen_page(cur, profile_id, device_ids):
    """The Listen-page list the app re-downloads after a restore: free tours,
    paid tours (now carrying restore grants), and news articles the profile
    owned across its devices."""
    paid_ids = _owned_paid_tour_ids(cur, device_ids)
    free_dl, paid_dl = _downloaded_tour_ids(cur, device_ids)
    # A paid tour the profile owned is paid even if it had not been downloaded
    # yet; a downloaded free tour is free. Union downloads with owned-paid.
    all_paid = paid_ids | paid_dl
    free_only = free_dl - all_paid
    return {
        "free_tours": sorted(free_only),
        "paid_tours": sorted(all_paid),
        "news_articles": _news_article_ids(cur, device_ids),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Core operations (DB) — callable directly by tests
# ──────────────────────────────────────────────────────────────────────────────

def generate_for_device(cur, device_id):
    """Generate (or ROTATE) the recovery code for the device's profile. Returns
    (code_plaintext, profile_id, rotated: bool). The plaintext is returned ONCE;
    only its salted hash is stored. Caller commits."""
    ensure_recovery_schema(cur)
    profile_id = _get_or_create_profile_id(cur, device_id)
    code = generate_recovery_code()
    salt = secrets.token_bytes(16)
    digest = hash_code(code, salt, PBKDF2_ITERATIONS)
    cur.execute(
        "SELECT 1 FROM recovery_codes WHERE consolidated_user_id = %s", (profile_id,)
    )
    rotated = cur.fetchone() is not None
    cur.execute(
        """
        INSERT INTO recovery_codes
            (consolidated_user_id, code_hash, code_salt, hash_algo, hash_iterations, created_at, rotated_at)
        VALUES (%s, %s, %s, 'pbkdf2_sha256', %s, NOW(), NULL)
        ON CONFLICT (consolidated_user_id) DO UPDATE
          SET code_hash = EXCLUDED.code_hash,
              code_salt = EXCLUDED.code_salt,
              hash_iterations = EXCLUDED.hash_iterations,
              rotated_at = NOW()
        """,
        (profile_id, psycopg2.Binary(digest), psycopg2.Binary(salt), PBKDF2_ITERATIONS),
    )
    return code, profile_id, rotated


def _match_code(cur, code):
    """Find the profile whose stored recovery hash matches `code`. Scans
    recovery_codes (one row per profile) and verifies each with its own salt in
    constant time. Returns (profile_id, iterations) or (None, None)."""
    cur.execute(
        "SELECT consolidated_user_id, code_hash, code_salt, hash_iterations FROM recovery_codes"
    )
    for profile_id, code_hash, code_salt, iterations in cur.fetchall():
        if verify_code(code, bytes(code_salt), bytes(code_hash), iterations):
            return profile_id, iterations
    return None, None


def _recent_attempt_count(cur, device_id):
    """How many restore attempts this device made in the last hour."""
    cur.execute(
        "SELECT COUNT(*) FROM restore_attempts "
        "WHERE device_id = %s AND created_at >= NOW() - INTERVAL '1 hour'",
        (device_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _recent_restore_count(cur, profile_id):
    """How many successful restores this profile had in the last 30 days."""
    cur.execute(
        "SELECT COUNT(*) FROM profile_restores "
        "WHERE consolidated_user_id = %s AND created_at >= NOW() - INTERVAL '30 days'",
        (profile_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _log_attempt(cur, device_id, outcome):
    cur.execute(
        "INSERT INTO restore_attempts (device_id, outcome) VALUES (%s, %s)",
        (device_id, outcome),
    )


def restore_for_device(cur, new_device_id, code):
    """Execute a restore. Returns (status, payload):
       status is one of 'restored' | 'bad_code' | 'rate_limited' | 'refused_abuse'.
    Enforces the per-device rate limit FIRST (so a flood of wrong codes is
    throttled), then validates the code, then the >2/30d abuse guard, then links
    the new device, unlinks the old, issues grants, logs the restore. Caller
    commits (on 'restored'); on any non-restored outcome the attempt is logged
    and the caller should still commit the attempt row."""
    ensure_recovery_schema(cur)

    # 1. Per-device rate limit (count this request's prior attempts in the hour).
    if _recent_attempt_count(cur, new_device_id) >= RESTORE_RATE_LIMIT_PER_HOUR:
        _log_attempt(cur, new_device_id, "rate_limited")
        return "rate_limited", {
            "error": "rate_limited",
            "message": "Too many attempts. Please wait an hour and try again.",
        }

    # 2. Validate the code.
    profile_id, _iters = _match_code(cur, code)
    if not profile_id:
        _log_attempt(cur, new_device_id, "bad_code")
        return "bad_code", {
            "error": "invalid_code",
            "message": "That recovery code was not recognised.",
        }

    # 3. Abuse guard: more than N restores in 30 days → Contact support.
    if _recent_restore_count(cur, profile_id) >= RESTORE_MAX_PER_30_DAYS:
        _log_attempt(cur, new_device_id, "refused_abuse")
        return "refused_abuse", {
            "error": "too_many_restores",
            "message": "This profile has been restored too many times recently. "
                       "Please contact support.",
        }

    # 4. Link the new device + unlink the previous device(s).
    prior_devices = _linked_device_ids(cur, profile_id)
    # The devices to unlink = every currently-linked device that is NOT the new
    # one (one profile lives on one phone at a time).
    to_unlink = {d for d in prior_devices if d and d != new_device_id}

    # Point the profile's primary device at the new phone.
    cur.execute(
        "UPDATE user_consolidation_map SET primary_device_id = %s, last_merged_at = NOW() "
        "WHERE consolidated_user_id = %s",
        (new_device_id, profile_id),
    )
    # Record the new device as a (re)linked member, if not already an active one.
    cur.execute(
        "SELECT 1 FROM device_consolidation_history "
        "WHERE consolidated_user_id = %s AND merged_device_id = %s AND unlinked_at IS NULL LIMIT 1",
        (profile_id, new_device_id),
    )
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO device_consolidation_history "
            "(consolidated_user_id, merged_device_id, domain, merged_at, unlinked_at) "
            "VALUES (%s, %s, 'recovery_restore', NOW(), NULL)",
            (profile_id, new_device_id),
        )
    # Unlink the old device(s): stamp their active history rows, and add an
    # unlinked marker row for a primary device that had no history row.
    for dev in to_unlink:
        cur.execute(
            "UPDATE device_consolidation_history SET unlinked_at = NOW() "
            "WHERE consolidated_user_id = %s AND merged_device_id = %s AND unlinked_at IS NULL",
            (profile_id, dev),
        )
        cur.execute(
            "SELECT 1 FROM device_consolidation_history "
            "WHERE consolidated_user_id = %s AND merged_device_id = %s LIMIT 1",
            (profile_id, dev),
        )
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO device_consolidation_history "
                "(consolidated_user_id, merged_device_id, domain, merged_at, unlinked_at) "
                "VALUES (%s, %s, 'recovery_unlink', NOW(), NOW())",
                (profile_id, dev),
            )

    # 5. Issue restore grants for every paid tour the profile owned.
    all_device_ids = prior_devices | {new_device_id}
    paid_ids = _owned_paid_tour_ids(cur, all_device_ids)
    grants = _issue_restore_grants(cur, profile_id, new_device_id, paid_ids)

    # 6. Build the Listen-page list and log the restore.
    listen_page = build_listen_page(cur, profile_id, all_device_ids)
    cur.execute(
        "INSERT INTO profile_restores "
        "(consolidated_user_id, new_device_id, unlinked_device_id, grants_issued) "
        "VALUES (%s, %s, %s, %s)",
        (profile_id, new_device_id,
         sorted(to_unlink)[0] if to_unlink else None, grants),
    )
    _log_attempt(cur, new_device_id, "success")

    return "restored", {
        "restored": True,
        "profile_id": profile_id,
        "unlinked_devices": sorted(to_unlink),
        "grants_issued": grants,
        "listen_page": listen_page,
    }


def profile_was_moved(cur, device_id):
    """True if this device was UNLINKED from its profile by a later restore (the
    "profile moved" state the old phone sees). Specifically: the device has at
    least one device_consolidation_history row and its MOST RECENT such row is
    unlinked (unlinked_at IS NOT NULL), AND it is not the current primary device
    of any profile. map_delivery uses this to stop offering re-download grants to
    a moved-away phone (tours already on it keep playing). Never raises."""
    try:
        ensure_recovery_schema(cur)
        # Still a primary device somewhere → not moved.
        cur.execute(
            "SELECT 1 FROM user_consolidation_map WHERE primary_device_id = %s LIMIT 1",
            (device_id,),
        )
        if cur.fetchone() is not None:
            return False
        cur.execute(
            "SELECT unlinked_at FROM device_consolidation_history "
            "WHERE merged_device_id = %s ORDER BY merged_at DESC, id DESC LIMIT 1",
            (device_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False  # never part of a consolidated profile
        return row[0] is not None
    except Exception:  # noqa: BLE001
        return False


def linked_device_ids_for_deletion(cur, secret_id):
    """Every device id that must be wiped when deleting the account behind
    `secret_id`, resolving the CONSOLIDATED identity across ALL linked devices
    (June design note). If secret_id is a device in a profile (primary or a
    linked/merged device, past or present), returns the whole set of that
    profile's device ids plus secret_id. If secret_id is itself a
    consolidated_user_id, returns that profile's device ids plus secret_id. If it
    belongs to no profile, returns just {secret_id}. Never raises — on error
    returns {secret_id} so deletion still removes the current device."""
    ids = {secret_id}
    try:
        ensure_recovery_schema(cur)
        # Is secret_id itself a profile id?
        cur.execute(
            "SELECT 1 FROM user_consolidation_map WHERE consolidated_user_id = %s LIMIT 1",
            (secret_id,),
        )
        if cur.fetchone() is not None:
            profile_id = secret_id
        else:
            # Else resolve the profile from the device id (primary or ANY history
            # row — a deleting user wants every device of theirs gone, even ones
            # that were unlinked by a restore).
            profile_id = None
            cur.execute(
                "SELECT consolidated_user_id FROM user_consolidation_map "
                "WHERE primary_device_id = %s LIMIT 1",
                (secret_id,),
            )
            r = cur.fetchone()
            if r:
                profile_id = r[0]
            if profile_id is None:
                cur.execute(
                    "SELECT consolidated_user_id FROM device_consolidation_history "
                    "WHERE merged_device_id = %s ORDER BY merged_at DESC LIMIT 1",
                    (secret_id,),
                )
                r = cur.fetchone()
                if r:
                    profile_id = r[0]
        if profile_id:
            ids.add(profile_id)
            cur.execute(
                "SELECT primary_device_id FROM user_consolidation_map "
                "WHERE consolidated_user_id = %s",
                (profile_id,),
            )
            for r in cur.fetchall():
                if r[0]:
                    ids.add(r[0])
            # ALL history rows (linked or unlinked) — delete every device the
            # profile ever spanned.
            cur.execute(
                "SELECT merged_device_id FROM device_consolidation_history "
                "WHERE consolidated_user_id = %s",
                (profile_id,),
            )
            for r in cur.fetchall():
                if r[0]:
                    ids.add(r[0])
    except Exception as e:  # noqa: BLE001
        logger.warning("linked_device_ids_for_deletion fell back for %s: %s", secret_id, e)
    return ids


# ──────────────────────────────────────────────────────────────────────────────
# HTTP surface
# ──────────────────────────────────────────────────────────────────────────────

def register_recovery_routes(app):
    """Register the recovery-code endpoints on the orchestrator Flask app.
    Mirrors the defensive register_*_routes pattern used by pricing/ratings."""

    @app.route("/recovery-code/generate", methods=["POST", "OPTIONS"])
    def recovery_code_generate():  # noqa: ANN001
        if request.method == "OPTIONS":
            return ("", 204)
        data = request.get_json(silent=True) or {}
        user_id = (data.get("user_id") or "").strip()
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        conn = None
        try:
            conn = _get_conn()
            cur = conn.cursor()
            code, profile_id, rotated = generate_for_device(cur, user_id)
            conn.commit()
            cur.close()
            return jsonify({
                "code": code,
                "profile_id": profile_id,
                "rotated": rotated,
                "created_at": datetime.utcnow().isoformat() + "Z",
            }), 201
        except Exception as e:  # noqa: BLE001
            if conn:
                conn.rollback()
            logger.error("recovery-code generate failed: %s", e)
            return jsonify({"error": "generate_failed",
                            "message": "Could not create a recovery code. Please try again."}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    @app.route("/recovery-code/status", methods=["GET", "OPTIONS"])
    def recovery_code_status():  # noqa: ANN001
        if request.method == "OPTIONS":
            return ("", 204)
        user_id = (request.args.get("user_id") or "").strip()
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        conn = None
        try:
            conn = _get_conn()
            cur = conn.cursor()
            ensure_recovery_schema(cur)
            profile_id = _resolve_profile_id(cur, user_id)
            has_code = False
            created_at = None
            rotated_at = None
            if profile_id:
                cur.execute(
                    "SELECT created_at, rotated_at FROM recovery_codes "
                    "WHERE consolidated_user_id = %s",
                    (profile_id,),
                )
                row = cur.fetchone()
                if row:
                    has_code = True
                    created_at = row[0].isoformat() if row[0] else None
                    rotated_at = row[1].isoformat() if row[1] else None
            conn.commit()
            cur.close()
            return jsonify({
                "has_code": has_code,
                "profile_id": profile_id,
                "created_at": created_at,
                "rotated_at": rotated_at,
            }), 200
        except Exception as e:  # noqa: BLE001
            if conn:
                conn.rollback()
            logger.error("recovery-code status failed: %s", e)
            return jsonify({"error": "status_failed"}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    @app.route("/recovery-code/restore", methods=["POST", "OPTIONS"])
    def recovery_code_restore():  # noqa: ANN001
        if request.method == "OPTIONS":
            return ("", 204)
        data = request.get_json(silent=True) or {}
        user_id = (data.get("user_id") or "").strip()
        code = (data.get("code") or "").strip()
        if not user_id or not code:
            return jsonify({"error": "user_id and code required"}), 400
        conn = None
        try:
            conn = _get_conn()
            cur = conn.cursor()
            status, payload = restore_for_device(cur, user_id, code)
            conn.commit()  # commit the attempt row (and the restore, if any)
            cur.close()
            http = {
                "restored": 200,
                "bad_code": 401,
                "rate_limited": 429,
                "refused_abuse": 409,
            }.get(status, 400)
            return jsonify(payload), http
        except Exception as e:  # noqa: BLE001
            if conn:
                conn.rollback()
            logger.error("recovery-code restore failed: %s", e)
            return jsonify({"error": "restore_failed",
                            "message": "Could not restore. Please try again."}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    return app
