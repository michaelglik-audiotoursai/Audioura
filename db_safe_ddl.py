"""
db_safe_ddl — safe runtime DDL for the generator path (LOCAL-797).

Background (found live on the Mac, 2026-10-28 10:55–11:12):
    A 2-stop Arnold Arboretum tour sat in poi_selection for 26 minutes. In
    pg_stat_activity, one connection sat "idle in transaction" after a
    stop_corpus SELECT (holding an AccessShare lock), while another ran
    `ALTER TABLE venue_corpus ALTER COLUMN tier TYPE VARCHAR(20)` — issued
    UNCONDITIONALLY once per process by venue_resolver._ensure_table. The ALTER
    needs an AccessExclusive lock, queued behind the idle reader, and every
    other `SELECT ... FROM venue_corpus` queued behind the waiting ALTER. All
    tours froze until the ALTER was cancelled.

The rule this module enforces:
    NEVER let a runtime DDL statement block a tour. Any DDL a running generator
    issues must:
      1. run inside its OWN short transaction (so it cannot be left dangling),
      2. set a short SET LOCAL lock_timeout (+ statement_timeout) so it gives up
         in a few seconds instead of queueing behind a reader for minutes,
      3. be skipped entirely when a cheap `needed_check_sql` says it is a no-op
         (e.g. the column is already wide enough), and
      4. on a lock timeout (or any error) log and CONTINUE — a cold-start schema
         touch is best-effort, not a reason to hang.

`safe_ddl` is import-safe when psycopg2 is missing and makes no assumption about
the connection's autocommit mode: it saves/restores it so the helper is always
run in its own explicit transaction.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Keep these short. The whole point is to give up fast rather than queue behind
# an idle-in-transaction reader (the LOCAL-797 freeze).
DEFAULT_LOCK_TIMEOUT = "3s"
DEFAULT_STATEMENT_TIMEOUT = "10s"

# [LOCAL-797] Connection options every generator-path connection should carry so
# a forgotten transaction can never hold a lock for minutes (belt-and-braces for
# the cloud, where we cannot watch the process): the server kills a transaction
# left idle for 60s, and any stray DDL gives up after 3s instead of queueing.
# Pass as the libpq `options` keyword to psycopg2.connect(...).
CONNECT_OPTIONS = "-c idle_in_transaction_session_timeout=60000 -c lock_timeout=3000"


def harden_read_connection(conn):
    """Make a connection safe for pure reads: autocommit on, so a SELECT never
    leaves an open transaction holding an AccessShare lock (the LOCAL-797
    idle-in-transaction freeze). Safe no-op if the connection cannot be changed.
    Returns the same connection for convenient inline use."""
    if conn is None:
        return conn
    try:
        conn.autocommit = True
    except Exception:
        pass
    return conn


def _table_name_of(sql: str) -> str:
    """Best-effort extraction of the target table name for log messages."""
    if not sql:
        return "?"
    m = re.search(
        r"\b(?:ALTER\s+TABLE|CREATE\s+INDEX(?:\s+CONCURRENTLY)?"
        r"(?:\s+IF\s+NOT\s+EXISTS)?\s+\S+\s+ON|CREATE\s+TABLE"
        r"(?:\s+IF\s+NOT\s+EXISTS)?)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"([A-Za-z_][\w\.]*)",
        sql,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    toks = sql.strip().split()
    return toks[-1] if toks else "?"


def _is_lock_timeout(exc: Exception) -> bool:
    """True when the exception is a Postgres lock_timeout / statement cancel."""
    # psycopg2 raises psycopg2.errors.LockNotAvailable (SQLSTATE 55P03) for
    # lock_timeout and QueryCanceled (57014) for statement_timeout. We match on
    # pgcode when available, else on the message text, so the helper stays
    # dependency-light and works even if psycopg2.errors is not importable.
    pgcode = getattr(exc, "pgcode", None)
    if pgcode in ("55P03", "57014"):
        return True
    msg = str(exc).lower()
    return (
        "lock timeout" in msg
        or "lock_timeout" in msg
        or "canceling statement due to" in msg
        or "could not obtain lock" in msg
    )


def safe_ddl(
    conn,
    sql: str,
    needed_check_sql: Optional[str] = None,
    *,
    lock_timeout: str = DEFAULT_LOCK_TIMEOUT,
    statement_timeout: str = DEFAULT_STATEMENT_TIMEOUT,
    label: str = "",
) -> bool:
    """Run one runtime DDL statement safely. Never raises on lock contention.

    Args:
        conn: a live psycopg2 connection. Its autocommit flag is saved and
            restored; the DDL always runs in its own explicit transaction.
        sql: the DDL statement (e.g. an ALTER TABLE or CREATE INDEX). Do NOT
            pass a bare `CREATE TABLE IF NOT EXISTS` through here in a hot path
            unless you want it lock-guarded too — it is harmless, just
            unnecessary, because creating a brand-new table takes no lock on an
            existing relation.
        needed_check_sql: optional SQL returning a single row/column that is
            truthy when the DDL IS needed and falsy when it is a no-op. When it
            evaluates falsy the DDL is SKIPPED (returns False). When it errors,
            we fall through and attempt the DDL (safer than skipping silently).
        lock_timeout / statement_timeout: Postgres interval strings.
        label: optional tag for log lines (e.g. "LOCAL-797").

    Returns:
        True  if the DDL was executed (committed).
        False if it was skipped (not needed) or abandoned (lock busy / error).
    """
    if conn is None:
        return False

    table = _table_name_of(sql)
    tag = f"[{label}] " if label else "[LOCAL-797] "

    # Preserve the caller's autocommit mode: we need a controlled transaction so
    # SET LOCAL + DDL + COMMIT behave deterministically regardless of how the
    # connection was configured elsewhere.
    try:
        prev_autocommit = conn.autocommit
    except Exception:
        prev_autocommit = None

    try:
        try:
            conn.autocommit = False
        except Exception:
            pass

        # 1) Optional no-op check — skip DDL that is not needed.
        if needed_check_sql:
            try:
                with conn.cursor() as cur:
                    cur.execute(needed_check_sql)
                    row = cur.fetchone()
                conn.commit()
                needed = bool(row and row[0])
                if not needed:
                    logger.info(f"  {tag}ddl not needed for {table} (skipped)")
                    return False
            except Exception as check_err:
                # Could not determine — roll back the probe and attempt the DDL.
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.info(
                    f"  {tag}ddl needed-check failed for {table} "
                    f"({type(check_err).__name__}: {check_err}); attempting DDL"
                )

        # 2) Run the DDL in its own transaction with a short lock timeout.
        try:
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL lock_timeout = '{lock_timeout}'")
                cur.execute(f"SET LOCAL statement_timeout = '{statement_timeout}'")
                cur.execute(sql)
            conn.commit()
            logger.info(f"  {tag}ddl applied to {table}")
            return True
        except Exception as ddl_err:
            try:
                conn.rollback()
            except Exception:
                pass
            if _is_lock_timeout(ddl_err):
                logger.warning(f"  {tag}ddl skipped {table} (lock busy)")
            else:
                logger.warning(
                    f"  {tag}ddl skipped {table} "
                    f"({type(ddl_err).__name__}: {ddl_err})"
                )
            return False
    finally:
        if prev_autocommit is not None:
            try:
                conn.autocommit = prev_autocommit
            except Exception:
                pass
