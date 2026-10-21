#!/usr/bin/env python3
"""support_id.py — LOCAL-729 / D692: the public Support ID per device.

A Support ID is a SHORT PUBLIC ALIAS of a device, e.g. ``AU-7K3Q``, shown in the
app's About screen with a Copy button. A buyer who wants a reimbursement gives us
their Support ID (or a store order number); the admin reimbursement tools resolve
it back to the device. It is NEVER the secret device id (``users.secret_id`` /
the device ``user_id``) — a public alias we can quote in a support email without
leaking the private identity.

Shape: ``AU-`` + 4 chars from an UNAMBIGUOUS base-28 alphabet (no 0/O/1/I/L to
avoid read-aloud/typing errors). 28^4 = 614,656 codes — ample for the device
population, and generation RETRIES on the astronomically unlikely collision
(support_ids.support_id is UNIQUE), so a Support ID is always unique.

One alias per device: ``ensure_support_id(cur, user_id)`` returns the existing
alias or allocates one, idempotently (support_ids.user_id is UNIQUE). Resolution
goes both ways: an ``AU-...`` string resolves via the table; anything else is
treated as already being a device id and returned as-is (so the admin tools
accept EITHER a Support ID OR the raw device id).

Pure DB, no network, no model. The caller owns the transaction (commit).
"""
from __future__ import annotations

import re
import secrets

# Unambiguous alphabet: A–Z and 2–9, minus the easily-confused O/I/L and 0/1.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 31 chars, no O I L 0 1
_PREFIX = "AU-"
_BODY_LEN = 4
# A well-formed Support ID: the prefix then BODY_LEN alphabet chars (case
# handled by normalisation). Used to tell a Support ID from a raw device id.
_SUPPORT_ID_RE = re.compile(r"^AU-[" + _ALPHABET + r"]{%d}$" % _BODY_LEN)


def generate_support_id() -> str:
    """A fresh, well-formed Support ID (``AU-XXXX``). Not guaranteed unique on
    its own — ``ensure_support_id`` retries against the DB's UNIQUE index."""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_BODY_LEN))
    return _PREFIX + body


def is_support_id(value) -> bool:
    """True if ``value`` looks like a Support ID (``AU-XXXX``), case-insensitive."""
    if not isinstance(value, str):
        return False
    return bool(_SUPPORT_ID_RE.match(value.strip().upper()))


def normalise(value: str) -> str:
    """Canonical form of a typed Support ID (trim + upper-case). A device id is
    returned unchanged (it is not an ``AU-`` string)."""
    v = (value or "").strip()
    return v.upper() if is_support_id(v) else v


def ensure_support_id(cur, user_id: str, max_tries: int = 20) -> str:
    """Return the device's Support ID, allocating one on first call. Idempotent:
    the same device always maps to the same alias (support_ids.user_id UNIQUE).
    Retries generation on the (vanishingly rare) support_id collision. The caller
    commits."""
    if not user_id:
        raise ValueError("user_id is required")
    # Already has one?
    cur.execute("SELECT support_id FROM support_ids WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    if row:
        return row[0]
    # Allocate, retrying on a UNIQUE(support_id) collision. ON CONFLICT on the
    # user_id does nothing but lets a concurrent allocator win the race; we then
    # re-read to return whatever alias the device actually holds.
    for _ in range(max_tries):
        candidate = generate_support_id()
        cur.execute(
            """INSERT INTO support_ids (support_id, user_id)
               VALUES (%s, %s)
               ON CONFLICT (user_id) DO NOTHING
               RETURNING support_id""",
            (candidate, user_id),
        )
        got = cur.fetchone()
        if got:
            return got[0]
        # Either the user already has one (concurrent insert) — re-read and
        # return it — or the support_id itself collided — try a new candidate.
        cur.execute("SELECT support_id FROM support_ids WHERE user_id = %s",
                    (user_id,))
        existing = cur.fetchone()
        if existing:
            return existing[0]
        # support_id collided with a DIFFERENT device; loop with a new candidate.
    raise RuntimeError("could not allocate a unique Support ID")


def resolve_to_user_id(cur, token: str):
    """Resolve an admin-supplied identifier to a device ``user_id``.

    * An ``AU-...`` Support ID resolves via support_ids → the device id, or None
      if unknown.
    * Anything else is assumed to ALREADY be a device id and returned as-is (the
      admin tools accept either form). An empty/None token returns None.
    """
    if not token:
        return None
    t = token.strip()
    if is_support_id(t):
        cur.execute("SELECT user_id FROM support_ids WHERE support_id = %s",
                    (t.upper(),))
        row = cur.fetchone()
        return row[0] if row else None
    # Not a Support ID → treat it as the raw device id.
    return t
