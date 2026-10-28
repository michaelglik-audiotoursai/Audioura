"""
Stop Pool Rejected (LOCAL-792 / D726 amended, Michael 2026-10-27).
==================================================================
"Why do we keep incorrect material for future usage?" (Michael). The stop pool
(LOCAL-590, ``stop_pool_store``) keeps whatever a delivered tour contained; nothing
ever marked a stop BAD. Tour 463 (War Remnants Museum) reused a news headline and a
fabricated entry, because the pool had no notion of "this stop is incorrect; never
reuse it".

D726 (amended) rules three cases three different ways — and ONLY ONE of them is
this module's job:

  * OUT OF SCOPE for THIS tour (real place, too far / off-route) — SKIP for this
    tour only (``stop_pool_orchestrator._revalidate_pooled_scope``, LOCAL-788). The
    stop STAYS in the pool. This module is NOT involved.
  * WRONG PIN (real place, good research, wrong coordinates) — corrected IN PLACE
    (``fix_stop_coords.py``); the stop STAYS in the pool. NOT involved.
  * INCORRECT CONTENT (not a place / not this venue / wrong facts) — MOVED out of
    the pool: its row is COPIED here (all columns + reason/by/at/source tour), then
    REMOVED from ``stop_pool``. THIS module does exactly that move, and its inverse.
  * FILED UNDER THE WRONG VENUE — re-filed when it resolves to one place, else
    treated as incorrect content (moved here).

This module is the ONE place a ``stop_pool`` row is ever removed, and only after
its copy here is verified, in a SINGLE transaction. It never touches
``audio_tours``. It also exposes the lookup every reuse read and the LOCAL-778
miner use to SKIP a quarantined (pool_key, title_norm) / (venue_identity,
title_norm), so a rejected stop can neither be returned to a reuse nor re-mined
back into the pool from a delivered tour.

Table discipline: additive self-healing DDL (identical to migration 056). The only
DELETE this module (and the whole system) issues against ``stop_pool`` is the
move's own delete, guarded by a verified copy inside one transaction; ``restore``
deletes from ``stop_pool_rejected`` only, after re-inserting into ``stop_pool``.
"""
import logging
from typing import Dict, List, Optional, Set, Tuple

import psycopg2

logger = logging.getLogger(__name__)


# The stop_pool columns, in order — the exact set copied on a move (and copied
# back on a restore). Kept here as the single source of truth so a schema change
# in stop_pool is mirrored by editing ONE list. Mirrors stop_pool_store._ensure_table.
POOL_COLUMNS: Tuple[str, ...] = (
    "pool_key", "title_norm", "venue_identity", "tour_type", "pool_version",
    "title", "artist", "year", "narration", "raw_block",
    "address", "coordinates", "type_specialty", "specific_examples",
    "operational_details", "sources_json", "story_elements_json",
    "generated_at", "hit_count", "order_seq", "research_cost_usd",
    "stop_record_json", "news_generated_at",
)

# The rejection-provenance columns stop_pool_rejected adds on top of POOL_COLUMNS.
REJECT_COLUMNS: Tuple[str, ...] = (
    "reject_reason", "rejected_by", "rejected_at", "source_tour_id",
)


# ── Schema (additive; identical to migration 056; never DELETE/DROP) ─────────

def ensure_table(conn) -> None:
    """Create the additive ``stop_pool_rejected`` table if absent (idempotent).

    Identical to migration 056 so a tool/service self-heals the table on any
    Postgres whether or not the migration has run. ``stop_pool``'s columns verbatim
    (so a moved row is a straight copy) plus reject_reason/by/at/source_tour_id, PK
    (pool_key, title_norm). Also ensures ``stop_pool`` itself exists (via the store)
    so the move/restore SQL always has both tables.
    """
    # Make sure stop_pool exists too — the move copies out of it and restore copies
    # back into it; a fresh test DB may have neither table yet.
    try:
        import stop_pool_store as pool
        pool._ensure_table(conn)
    except Exception:
        pass
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS stop_pool_rejected (
                pool_key            TEXT        NOT NULL,
                title_norm          TEXT        NOT NULL,
                venue_identity      TEXT        NOT NULL,
                tour_type           TEXT        NOT NULL,
                pool_version        INTEGER     NOT NULL,
                title               TEXT        NOT NULL,
                artist              TEXT        DEFAULT '',
                year                TEXT        DEFAULT '',
                narration           TEXT        NOT NULL,
                raw_block           TEXT,
                address             TEXT        DEFAULT '',
                coordinates         TEXT        DEFAULT '',
                type_specialty      TEXT        DEFAULT '',
                specific_examples   TEXT        DEFAULT '',
                operational_details TEXT        DEFAULT '',
                sources_json        TEXT,
                story_elements_json TEXT,
                generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                hit_count           INTEGER     DEFAULT 0,
                order_seq           INTEGER     DEFAULT 0,
                research_cost_usd   NUMERIC(12, 6) DEFAULT 0,
                stop_record_json    TEXT,
                news_generated_at   TIMESTAMPTZ,
                reject_reason       TEXT,
                rejected_by         TEXT,
                rejected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                source_tour_id      INTEGER,
                PRIMARY KEY (pool_key, title_norm)
            )
            """
        )
        # Guarded ADD COLUMN for a table from an earlier partial run (idempotent).
        # [LOCAL-792 / LEAD 18:5x] Same lock hazard as stop_pool: ALTER / CREATE
        # INDEX on an EXISTING table takes an ACCESS EXCLUSIVE lock, which waits
        # forever behind an idle-in-transaction connection and then blocks every
        # reader queued behind it. Bound the wait (SET LOCAL lock_timeout = 3s) and
        # wrap the lock-taking DDL in a SAVEPOINT so a lock_timeout rolls back only
        # the DDL — the columns already exist on any migrated DB (migration 056 is
        # the authoritative schema), so the move/restore/lookup paths carry on.
        try:
            cur.execute("SAVEPOINT stop_pool_rejected_ddl")
            cur.execute("SET LOCAL lock_timeout = '3s'")
            for _ddl in (
                "ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS order_seq INTEGER DEFAULT 0",
                "ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS research_cost_usd NUMERIC(12, 6) DEFAULT 0",
                "ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS stop_record_json TEXT",
                "ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS news_generated_at TIMESTAMPTZ",
                "ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS reject_reason TEXT",
                "ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS rejected_by TEXT",
                "ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
                "ALTER TABLE stop_pool_rejected ADD COLUMN IF NOT EXISTS source_tour_id INTEGER",
                "CREATE INDEX IF NOT EXISTS idx_stop_pool_rejected_key ON stop_pool_rejected (pool_key)",
                "CREATE INDEX IF NOT EXISTS idx_stop_pool_rejected_identity ON stop_pool_rejected (venue_identity, title_norm)",
            ):
                cur.execute(_ddl)
            cur.execute("RELEASE SAVEPOINT stop_pool_rejected_ddl")
        except psycopg2.Error as _ddl_err:
            cur.execute("ROLLBACK TO SAVEPOINT stop_pool_rejected_ddl")
            logger.warning(
                "[LOCAL-792] stop_pool_rejected self-healing DDL skipped (%s); "
                "relying on migration 056 for the schema", _ddl_err)
    conn.commit()


def _table_exists(conn, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (name,))
        return cur.fetchone()[0] is not None


def _qualified_cols(alias: str) -> str:
    """POOL_COLUMNS as ``alias.col, alias.col, …`` so a SELECT over a join (the
    unnest keys share the pool_key/title_norm names) is never ambiguous."""
    return ", ".join(f"{alias}.{c}" for c in POOL_COLUMNS)


# ── Reuse / miner SKIP lookup ────────────────────────────────────────────────

def rejected_title_norms(
    conn,
    pool_keys: List[str],
) -> Set[str]:
    """Return the set of ``title_norm`` values quarantined under ANY of ``pool_keys``.

    This is the lookup every reuse read and the LOCAL-778 miner use to SKIP a
    rejected stop. Keyed only by ``title_norm`` (the same under the ``qid:`` and
    ``loc:`` pool keys for one stop), so a stop rejected under one key is skipped
    when read under the other — the D582 dual-key robustness the pool itself uses.

    Returns an empty set when the table does not exist yet (pre-migration DB) so a
    caller that has not run migration 056 behaves exactly as before. Never raises
    for a missing table; a real DB error propagates to the caller's own guard.
    """
    if not pool_keys or not _table_exists(conn, "stop_pool_rejected"):
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT title_norm FROM stop_pool_rejected WHERE pool_key = ANY(%s)",
            (list(pool_keys),),
        )
        return {r[0] for r in cur.fetchall()}


def rejected_norms_by_identity(conn, venue_identity: str) -> Set[str]:
    """Return the ``title_norm`` values quarantined for a venue IDENTITY (across any
    tour_type / pool version). Used by the LOCAL-778 miner, which works from a
    delivered tour's venue identity without knowing the exact pool_key.

    Empty set when the table is absent (pre-migration DB)."""
    if not venue_identity or not _table_exists(conn, "stop_pool_rejected"):
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT title_norm FROM stop_pool_rejected WHERE venue_identity = %s",
            (venue_identity,),
        )
        return {r[0] for r in cur.fetchall()}


def _counts(conn) -> Tuple[int, int]:
    """(stop_pool rows, stop_pool_rejected rows) — for before/after reporting."""
    pool_n = rej_n = 0
    with conn.cursor() as cur:
        if _table_exists(conn, "stop_pool"):
            cur.execute("SELECT COUNT(*) FROM stop_pool")
            pool_n = cur.fetchone()[0]
        if _table_exists(conn, "stop_pool_rejected"):
            cur.execute("SELECT COUNT(*) FROM stop_pool_rejected")
            rej_n = cur.fetchone()[0]
    return pool_n, rej_n


# ── Move: copy-then-remove, verified, in ONE transaction ─────────────────────

def move_to_rejected(
    conn,
    keys: List[Tuple[str, str]],
    reason: str,
    rejected_by: str,
    source_tour_id: Optional[int] = None,
) -> int:
    """Move the given ``(pool_key, title_norm)`` rows from ``stop_pool`` to
    ``stop_pool_rejected``, in ONE transaction, verifying the copy count equals the
    delete count before COMMIT. Returns the number of rows moved.

    This is the ONLY code path that DELETEs a ``stop_pool`` row, and it does so
    strictly AFTER its copy exists in ``stop_pool_rejected`` and AFTER verifying the
    counts match. On ANY mismatch it raises (the caller must roll back) so a row is
    never removed from the pool without a verified copy — the ticket's hard rule.

    Idempotent per key: a key already quarantined (present in stop_pool_rejected)
    or absent from stop_pool contributes 0 to the move. The reject-provenance
    columns are set from ``reason`` / ``rejected_by`` / ``source_tour_id``;
    ``rejected_at`` defaults to NOW().

    The caller owns the transaction (commit/rollback) and the connection so the
    whole move can be composed with other work (e.g. the automatic reuse-path
    reject records provenance in the same connection). This function does NOT
    commit.
    """
    ensure_table(conn)
    if not keys:
        return 0

    # Keep only keys that are actually present in stop_pool and NOT already
    # quarantined — so the move is idempotent and the count check is exact.
    movable: List[Tuple[str, str]] = []
    with conn.cursor() as cur:
        for pk, tn in keys:
            cur.execute(
                "SELECT 1 FROM stop_pool WHERE pool_key = %s AND title_norm = %s",
                (pk, tn),
            )
            in_pool = cur.fetchone() is not None
            cur.execute(
                "SELECT 1 FROM stop_pool_rejected WHERE pool_key = %s AND title_norm = %s",
                (pk, tn),
            )
            already = cur.fetchone() is not None
            if in_pool and not already:
                movable.append((pk, tn))
    if not movable:
        return 0

    cols = ", ".join(POOL_COLUMNS)
    pk_list = [m[0] for m in movable]
    tn_list = [m[1] for m in movable]

    with conn.cursor() as cur:
        # 1. COPY: insert the full column set into stop_pool_rejected, stamping the
        #    rejection provenance. Selected by the exact (pool_key, title_norm)
        #    pairs via unnest so we only ever copy the rows we intend to delete.
        cur.execute(
            f"""
            INSERT INTO stop_pool_rejected (
                {cols}, reject_reason, rejected_by, rejected_at, source_tour_id
            )
            SELECT {_qualified_cols('sp')}, %s, %s, NOW(), %s
            FROM stop_pool sp
            JOIN unnest(%s::text[], %s::text[]) AS k(pool_key, title_norm)
              ON sp.pool_key = k.pool_key AND sp.title_norm = k.title_norm
            """,
            (reason, rejected_by, source_tour_id, pk_list, tn_list),
        )
        copied = cur.rowcount

        # 2. VERIFY the copies exist before any delete. Count the matching rows now
        #    present in stop_pool_rejected for these exact keys.
        cur.execute(
            """
            SELECT COUNT(*) FROM stop_pool_rejected r
            JOIN unnest(%s::text[], %s::text[]) AS k(pool_key, title_norm)
              ON r.pool_key = k.pool_key AND r.title_norm = k.title_norm
            """,
            (pk_list, tn_list),
        )
        verified = cur.fetchone()[0]
        if copied != len(movable) or verified < len(movable):
            raise RuntimeError(
                f"reject copy verification failed: intended={len(movable)} "
                f"copied={copied} verified_present={verified}; aborting (no delete)"
            )

        # 3. DELETE from stop_pool — ONLY now, and only the verified keys.
        cur.execute(
            """
            DELETE FROM stop_pool sp
            USING unnest(%s::text[], %s::text[]) AS k(pool_key, title_norm)
            WHERE sp.pool_key = k.pool_key AND sp.title_norm = k.title_norm
            """,
            (pk_list, tn_list),
        )
        deleted = cur.rowcount
        if deleted != len(movable):
            raise RuntimeError(
                f"reject delete count mismatch: intended={len(movable)} "
                f"deleted={deleted}; aborting (transaction will roll back)"
            )

    return len(movable)


def restore_from_rejected(
    conn,
    keys: List[Tuple[str, str]],
) -> int:
    """Move the given ``(pool_key, title_norm)`` rows BACK from
    ``stop_pool_rejected`` to ``stop_pool``, in ONE transaction. Returns the number
    of rows restored.

    The inverse of :func:`move_to_rejected`: the stop_pool columns are copied back
    verbatim (the rejection-provenance columns are dropped), the copy is verified,
    and only then is the ``stop_pool_rejected`` row deleted. Idempotent per key: a
    key absent from stop_pool_rejected, or already back in stop_pool, contributes 0.
    Does NOT commit (the caller owns the transaction).
    """
    ensure_table(conn)
    if not keys:
        return 0

    restorable: List[Tuple[str, str]] = []
    with conn.cursor() as cur:
        for pk, tn in keys:
            cur.execute(
                "SELECT 1 FROM stop_pool_rejected WHERE pool_key = %s AND title_norm = %s",
                (pk, tn),
            )
            in_rej = cur.fetchone() is not None
            cur.execute(
                "SELECT 1 FROM stop_pool WHERE pool_key = %s AND title_norm = %s",
                (pk, tn),
            )
            already = cur.fetchone() is not None
            if in_rej and not already:
                restorable.append((pk, tn))
    if not restorable:
        return 0

    cols = ", ".join(POOL_COLUMNS)
    pk_list = [m[0] for m in restorable]
    tn_list = [m[1] for m in restorable]

    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO stop_pool ({cols})
            SELECT {_qualified_cols('r')}
            FROM stop_pool_rejected r
            JOIN unnest(%s::text[], %s::text[]) AS k(pool_key, title_norm)
              ON r.pool_key = k.pool_key AND r.title_norm = k.title_norm
            """,
            (pk_list, tn_list),
        )
        copied = cur.rowcount
        cur.execute(
            """
            SELECT COUNT(*) FROM stop_pool sp
            JOIN unnest(%s::text[], %s::text[]) AS k(pool_key, title_norm)
              ON sp.pool_key = k.pool_key AND sp.title_norm = k.title_norm
            """,
            (pk_list, tn_list),
        )
        verified = cur.fetchone()[0]
        if copied != len(restorable) or verified < len(restorable):
            raise RuntimeError(
                f"restore copy verification failed: intended={len(restorable)} "
                f"copied={copied} verified_present={verified}; aborting (no delete)"
            )
        cur.execute(
            """
            DELETE FROM stop_pool_rejected r
            USING unnest(%s::text[], %s::text[]) AS k(pool_key, title_norm)
            WHERE r.pool_key = k.pool_key AND r.title_norm = k.title_norm
            """,
            (pk_list, tn_list),
        )
        deleted = cur.rowcount
        if deleted != len(restorable):
            raise RuntimeError(
                f"restore delete count mismatch: intended={len(restorable)} "
                f"deleted={deleted}; aborting (transaction will roll back)"
            )
    return len(restorable)


# ── Automatic reuse-path reject (no human) ───────────────────────────────────

def auto_reject_rows(
    db_url: str,
    rows: List[Dict],
    location: str,
    tour_type: str,
    reason: str,
    rejected_by: str,
    qid: Optional[str] = None,
    source_tour_id: Optional[int] = None,
) -> int:
    """Move the given reuse-candidate ``rows`` (as returned by
    ``stop_pool_store.get_pool_stops``) out of ``stop_pool`` into
    ``stop_pool_rejected`` with ``reason``/``rejected_by``.

    Used by the reuse path when a candidate FAILS the junk-title / other-venue
    check (D726 "incorrect content" / "wrong venue"). Each row's
    (pool_key, title_norm) is computed from the venue identity exactly as the pool
    store keys it — under BOTH the QID key and the location key, so the stop is
    moved whichever key it was stored under. The whole move runs in ONE
    transaction via :func:`move_to_rejected` (verified copy before delete).

    Best-effort and non-fatal: any failure rolls the transaction back and returns
    0 — an automatic quarantine must never fail a tour that is otherwise fine. The
    row simply stays in the pool (and is still skipped from THIS tour by the caller
    which dropped it before counting K).
    """
    if not db_url or not rows:
        return 0
    try:
        import stop_pool_store as pool
    except Exception as e:  # pragma: no cover
        logger.warning(f"[LOCAL-792] pool store unavailable for auto-reject ({e})")
        return 0

    keys: List[Tuple[str, str]] = []
    for r in rows:
        tnorm = pool._title_norm(r.get("title") or "")
        if not tnorm:
            continue
        for ident in _identities(pool, location, qid):
            keys.append((pool._pool_key(ident, tour_type), tnorm))
    if not keys:
        return 0

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        moved = move_to_rejected(
            conn, keys, reason=reason, rejected_by=rejected_by,
            source_tour_id=source_tour_id)
        conn.commit()
        if moved:
            logger.info(
                f"[LOCAL-792] auto-rejected {moved} stop(s) from the pool "
                f"(reason={reason!r} by={rejected_by!r})")
        return moved
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.warning(f"[LOCAL-792] auto-reject skipped ({e}); pool unchanged")
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _identities(pool, location: str, qid: Optional[str]) -> List[str]:
    """Both venue identities a stop may be keyed under: the QID identity (when a
    QID is supplied) and the normalised-location identity. Mirrors
    get_pool_stops' dual-key read."""
    idents: List[str] = []
    if qid:
        idents.append(pool.venue_identity(location, qid))
    loc_ident = pool.venue_identity(location)
    if loc_ident not in idents:
        idents.append(loc_ident)
    return idents
