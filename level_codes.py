"""
level_codes.py — LOCAL-604 level-code core (shared, framework-free) + CLI.
=========================================================================

Design of record: SUBSCRIPTION_LEVELS.md (D613) + LEAD ruling D619.

LEAD generates "level codes" that move a device to ANY level — including the
hidden tester and admin levels — by typing the code into the Free plan's single
code box. This module is the SINGLE implementation of the level-code rules. It
is deliberately framework-free (no Flask) so it is shared by:

  * the user-api blueprint (entitlements_api.py, the /l2/claim route), and
  * this file's own CLI (`python3 level_codes.py create <level>`).

Like l2_seats.py it exists TWICE — repo root and user-tracking/ — kept
byte-identical by a mirror test, because the user-api container's build context
is ./user-tracking and cannot import repo-root modules.

CODE SHAPE (D619):
  * Plaintext code: AUD-XXXX-XXXX, Crockford base32 (no I/L/O/U — unambiguous),
    generated with the cryptographic RNG. Shown to LEAD exactly ONCE by the CLI
    and NEVER committed, logged or written to a file by the task.
  * Stored: the lowercase hex sha256 of the UPPERCASED, hyphen-normalised code —
    HASHES ONLY. There is no plaintext column (a test asserts this).

RULES (D619):
  * A match sets device_entitlement.level to the code's level — any level, no
    seat cap for the admin/tester/l3/l4 test-switching path (this is LEAD's own
    switch, not a public seat grant).
  * A switch to l3/l4 starts a TEST PACK exactly as a purchase does:
    pack_started_at = now, anniversary_at = now + 1 calendar month, counters
    reset, and a `purchases` row with store='level_code' is written so pack
    counting works identically to a real purchase.
  * Switching to l1/l2/tester/admin clears the pack window (no anniversary).
  * Codes are REUSABLE (Michael switches back and forth); each successful claim
    increments `uses`.
  * Codes are REVOCABLE: setting revoked_at refuses all further claims.

Every DB function takes a live psycopg2 cursor and runs inside the caller's
transaction — the caller owns commit/rollback — so the API can compose the
level switch atomically with its own writes.
"""

import os
import re
import sys
import hashlib
import secrets
import calendar
from datetime import datetime


# Crockford base32 alphabet (excludes I, L, O, U to avoid ambiguity).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Result codes for a claim attempt (mirrors the l2_seats LOCAL-580 pattern).
LEVEL_OK = 'ok'
LEVEL_NOT_FOUND = 'level_code_not_found'
LEVEL_REVOKED = 'level_code_revoked'


# ───────────────────────────────────────────────────────────────────────────
# Code shape: generate, normalise, hash
# ───────────────────────────────────────────────────────────────────────────
def generate_code():
    """Return a fresh random plaintext level code, AUD-XXXX-XXXX in Crockford
    base32. Uses secrets (CSPRNG). This is the ONLY place a plaintext code
    exists; the caller must show it once and never persist it."""
    body = ''.join(secrets.choice(_CROCKFORD) for _ in range(8))
    return f"AUD-{body[:4]}-{body[4:]}"


def normalise_code(code):
    """Canonicalise a user-typed code for hashing: strip spaces, uppercase, and
    keep only the AUD prefix + base32 body with single hyphens. Accepts the code
    with or without hyphens and in any case, so a user retyping it loosely still
    matches. Returns the canonical 'AUD-XXXX-XXXX' or None if it is not shaped
    like a level code at all."""
    if not code:
        return None
    s = re.sub(r'[\s-]', '', str(code)).upper()
    if not s.startswith('AUD'):
        return None
    body = s[3:]
    if len(body) != 8 or any(ch not in _CROCKFORD for ch in body):
        return None
    return f"AUD-{body[:4]}-{body[4:]}"


def hash_code(code):
    """Return the lowercase hex sha256 of the NORMALISED code, or None if the
    code is not shaped like a level code. This is what is stored and compared."""
    canon = normalise_code(code)
    if canon is None:
        return None
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


# ───────────────────────────────────────────────────────────────────────────
# Anniversary arithmetic (mirror of entitlements_api.add_one_calendar_month)
# ───────────────────────────────────────────────────────────────────────────
def _add_one_calendar_month(when):
    y, m, d = when.year, when.month, when.day
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    last_day = calendar.monthrange(ny, nm)[1]
    nd = min(d, last_day)
    return when.replace(year=ny, month=nm, day=nd)


# ───────────────────────────────────────────────────────────────────────────
# Store side (DB) — create, claim, revoke
# ───────────────────────────────────────────────────────────────────────────
def store_code_hash(cur, code_hash, level):
    """Insert a level-code hash for `level`. Idempotent on the hash (a repeated
    create of the same plaintext is a no-op that keeps the existing row). The
    caller owns the transaction."""
    cur.execute("""
        INSERT INTO level_codes (code_hash, level, created_at, uses)
        VALUES (%s, %s, NOW(), 0)
        ON CONFLICT (code_hash) DO NOTHING
    """, (code_hash, level))


def lookup_code(cur, code):
    """Return (level, revoked_at) for a typed code, or None if the code is not a
    level code or no hash matches. Pure read."""
    h = hash_code(code)
    if h is None:
        return None
    cur.execute("SELECT level, revoked_at FROM level_codes WHERE code_hash = %s", (h,))
    row = cur.fetchone()
    if not row:
        return None
    return {'level': row[0], 'revoked_at': row[1]}


def claim_level_code(cur, user_id, code, now=None):
    """Attempt to switch `user_id` to the level a level code grants.

    Returns {'ok': bool, 'code': <LEVEL_* enum>, 'level': str|None,
             'message': str}. On ok the device's level is set and (for l3/l4) a
    test pack is started with a store='level_code' purchases row. The caller
    owns the transaction and must COMMIT on ok.

    This is the FIRST code kind checked by /l2/claim: a code that is not shaped
    like a level code (hash_code -> None) or whose hash is unknown returns
    LEVEL_NOT_FOUND so the caller can fall through to the offer/referral paths.
    """
    info = lookup_code(cur, code)
    if info is None:
        return {'ok': False, 'code': LEVEL_NOT_FOUND, 'level': None,
                'message': 'Not a level code.'}
    if info['revoked_at'] is not None:
        return {'ok': False, 'code': LEVEL_REVOKED, 'level': None,
                'message': 'That code has been revoked.'}

    level = info['level']
    now = now or datetime.utcnow()
    h = hash_code(code)

    if level in ('l3', 'l4'):
        # Start a test pack exactly as a purchase does.
        anniversary = _add_one_calendar_month(now)
        cur.execute("""
            INSERT INTO device_entitlement
                (user_id, level, pack_started_at, anniversary_at,
                 fresh_used, edits_used, ops_used, last_activity_at)
            VALUES (%s, %s, %s, %s, 0, 0, 0, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                level = EXCLUDED.level,
                pack_started_at = EXCLUDED.pack_started_at,
                anniversary_at = EXCLUDED.anniversary_at,
                fresh_used = 0, edits_used = 0, ops_used = 0, updated_at = NOW()
        """, (user_id, level, now, anniversary))
        # Record the switch as a purchase so pack counting is identical to a buy.
        # transaction_id is UNIQUE; synthesize a per-switch id that cannot clash.
        product = 'l3_pack_10' if level == 'l3' else 'l4_round_25'
        txid = f"levelcode:{user_id}:{now.strftime('%Y%m%d%H%M%S%f')}"
        cur.execute("""
            INSERT INTO purchases (transaction_id, store, product, user_id, amount, raw_status)
            VALUES (%s, 'level_code', %s, %s, 0, 'level_code_switch')
            ON CONFLICT (transaction_id) DO NOTHING
        """, (txid, product, user_id))
    else:
        # l1/l2/tester/admin: set the level, clear any pack window.
        cur.execute("""
            INSERT INTO device_entitlement
                (user_id, level, pack_started_at, anniversary_at,
                 fresh_used, edits_used, ops_used, last_activity_at)
            VALUES (%s, %s, NULL, NULL, 0, 0, 0, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                level = EXCLUDED.level,
                pack_started_at = NULL, anniversary_at = NULL,
                fresh_used = 0, edits_used = 0, ops_used = 0, updated_at = NOW()
        """, (user_id, level))

    # Log the use (codes are reusable).
    cur.execute("UPDATE level_codes SET uses = uses + 1 WHERE code_hash = %s", (h,))
    return {'ok': True, 'code': LEVEL_OK, 'level': level,
            'message': f'Switched to {level} by level code.'}


def revoke_code_hash(cur, code_hash):
    """Revoke a code by its hash (idempotent). Returns True if a row was
    revoked now, False if the hash is unknown or already revoked."""
    cur.execute("""
        UPDATE level_codes SET revoked_at = NOW()
        WHERE code_hash = %s AND revoked_at IS NULL
    """, (code_hash,))
    return cur.rowcount > 0


# ───────────────────────────────────────────────────────────────────────────
# CLI — `python3 level_codes.py create <level>` and `revoke <hash>`
# ───────────────────────────────────────────────────────────────────────────
def _cli_db():
    import psycopg2
    url = os.getenv('DATABASE_URL')
    if not url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(2)
    return psycopg2.connect(url)


_VALID_LEVELS = ('l1', 'l2', 'l3', 'l4', 'tester', 'admin')


def _cmd_create(level):
    if level not in _VALID_LEVELS:
        print(f"Unknown level '{level}'. Valid: {', '.join(_VALID_LEVELS)}", file=sys.stderr)
        sys.exit(2)
    code = generate_code()           # exists only in memory
    code_hash = hash_code(code)
    conn = _cli_db()
    try:
        with conn.cursor() as cur:
            # Guard: the level must exist in plans (FK), else fail loudly.
            cur.execute("SELECT 1 FROM plans WHERE plan_id = %s", (level,))
            if not cur.fetchone():
                print(f"Level '{level}' is not a plan row. Run migrations first.", file=sys.stderr)
                sys.exit(2)
            store_code_hash(cur, code_hash, level)
        conn.commit()
    finally:
        conn.close()
    # Print the plaintext code EXACTLY ONCE, to stdout only. The hash is stored;
    # the plaintext is never persisted by this tool. (The hash is printed to
    # stderr so an operator can revoke later without re-deriving it.)
    print(code)
    print(f"(stored sha256: {code_hash}  level: {level})", file=sys.stderr)


def _cmd_revoke(code_hash):
    code_hash = code_hash.strip().lower()
    if len(code_hash) != 64 or any(c not in '0123456789abcdef' for c in code_hash):
        print("Expected a 64-char hex sha256 hash to revoke.", file=sys.stderr)
        sys.exit(2)
    conn = _cli_db()
    try:
        with conn.cursor() as cur:
            revoked = revoke_code_hash(cur, code_hash)
        conn.commit()
    finally:
        conn.close()
    print("revoked" if revoked else "no-op (unknown or already revoked)")


def _main(argv):
    if len(argv) >= 3 and argv[1] == 'create':
        return _cmd_create(argv[2])
    if len(argv) >= 3 and argv[1] == 'revoke':
        return _cmd_revoke(argv[2])
    print("Usage:\n"
          "  python3 level_codes.py create <l1|l2|l3|l4|tester|admin>\n"
          "  python3 level_codes.py revoke <sha256-hex-hash>", file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    _main(sys.argv)
