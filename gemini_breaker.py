#!/usr/bin/env python3
"""gemini_breaker.py — LOCAL-814: a process-wide circuit breaker for Gemini.

THE BUG IT EXISTS TO FIX. Gemini prepaid credit is depleted. On 2026-10-29 the
Mac meter logged 329 Gemini 402s in one day (237 from story_leads.py:380, 57
from story_leads.py:326, 35 unattributed) — every one of them a request to a
dead credit, each costing latency and degrading the tour, and each retried on
the NEXT tour because nothing remembered the account was dry.

A 402 "prepayment credits are depleted" / RESOURCE_EXHAUSTED does not get better
by asking again a second later. It is an ACCOUNT state, not a transient blip, so
the right response is to stop calling for a while and route every caller to its
non-Gemini fallback. A 429 (rate limit) IS transient, so it trips the breaker
for a much shorter window.

CONTRACT
--------
  * is_open() -> bool. True means "do not call Gemini; use the fallback". A
    caller checks this BEFORE issuing a request, and skips Gemini when it is open.
  * note_response(status_code, body) is called by the two Gemini HTTP sites in
    story_leads with the status of every response. A 402 trips the breaker for
    GEMINI_BREAKER_402_MINUTES (default 30); a 429 for
    GEMINI_BREAKER_429_MINUTES (default 2). Any other status is ignored.
  * trip(reason, window_s) opens the breaker directly (used by the HTTP sites
    when requests raises before a response object exists but the error names a
    402/429).

  The breaker is PROCESS-WIDE (a module-level singleton) AND cross-process: on a
  trip it also writes a small row to a DB flag table (gemini_breaker_flag) so
  SIBLING WORKERS — the task containers that share the same depleted key — see
  the open state and stop calling too. is_open() consults the in-process state
  first (free, no I/O) and falls back to the DB flag (best-effort, short timeout).

  On each NEW trip (an edge from closed→open, not a re-confirmation while already
  open) it:
    * logs EXACTLY ONCE:  [LOCAL-814] gemini disabled 30m: credit depleted
      (or "disabled 2m: rate limited" for a 429), and
    * writes ONE failure_events row (D723) via failure_log.record so the nightly
      triage reports it as external/credit (the message names the credit refusal,
      which failure_triage classifies as `budget` — the credit sub-owner of the
      external family — and the stored triage is 'external').

  Everything here is best-effort and NEVER raises into a caller: a breaker that
  crashes the generator is worse than the bug it guards. The DB flag and the
  failure_events write are both wrapped and time-bounded; the worst case is that
  the cross-process signal is missed and each process trips its own in-process
  breaker independently (still a 30-minute stop per process, which is the goal).

DEFAULT-SAFE. With a healthy key the breaker never trips, is_open() is always
False, and the two HTTP sites behave exactly as before. GEMINI_BREAKER_DISABLE=1
hard-disables it (is_open() always False, trips are no-ops) as an escape hatch.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional

__all__ = [
    "is_open", "note_response", "trip", "reset", "state",
    "window_for_status", "status_from_error",
]

# ── tunables (env-overridable; safe defaults from the ticket) ─────────────────
_MIN_402 = float(os.environ.get("GEMINI_BREAKER_402_MINUTES", "30") or "30")
_MIN_429 = float(os.environ.get("GEMINI_BREAKER_429_MINUTES", "2") or "2")
# DB flag connect + statement timeout, seconds. The contract is "never stall the
# caller" — a down/slow DB must not block a generation.
_DB_TIMEOUT_S = float(os.environ.get("GEMINI_BREAKER_DB_TIMEOUT", "1") or "1")

_FLAG_TABLE = "gemini_breaker_flag"
# Single-row table: a fixed key so a trip UPSERTs the one row. open_until is the
# epoch seconds the breaker stays open to; reason/status describe the last trip.
_FLAG_KEY = "gemini"

_LOG_PREFIX = "[LOCAL-814]"


def _disabled() -> bool:
    return os.environ.get("GEMINI_BREAKER_DISABLE", "").strip() == "1"


# ── in-process state ──────────────────────────────────────────────────────────
class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.open_until = 0.0      # epoch seconds; 0 = closed
        self.reason = ""           # human reason of the current/last trip
        self.status = 0            # last trip's HTTP status (402/429)

    def open_now(self, now: float) -> bool:
        return self.open_until > now


_S = _State()


# ── classification helpers ────────────────────────────────────────────────────
def window_for_status(status: int) -> float:
    """Seconds the breaker should stay open for an HTTP `status`. 402 → the long
    credit window, 429 → the short rate-limit window, anything else → 0 (no trip)."""
    if status == 402:
        return _MIN_402 * 60.0
    if status == 429:
        return _MIN_429 * 60.0
    return 0.0


def _is_credit_depleted(status: int, body: str) -> bool:
    """A 402 is always a credit/payment refusal here. A few deployments surface
    the same 'prepayment credits are depleted' / RESOURCE_EXHAUSTED message under
    a 429 or a 400; treat those as credit too when the body names it, so the long
    window (not the 2-minute one) is used."""
    if status == 402:
        return True
    b = (body or "").lower()
    return ("prepayment" in b and "credit" in b) or "credits are depleted" in b \
        or "resource_exhausted" in b and "credit" in b


def status_from_error(err: BaseException) -> int:
    """Best-effort: extract an HTTP status (402/429) from a requests exception or
    its message, for the trip path where only an exception is in hand. Returns 0
    when nothing credit/rate-limit-ish is found."""
    # requests.HTTPError carries .response with a status_code.
    resp = getattr(err, "response", None)
    code = getattr(resp, "status_code", None)
    try:
        if code is not None:
            code = int(code)
            if code in (402, 429):
                return code
    except (TypeError, ValueError):
        pass
    msg = str(err or "").lower()
    if "402" in msg or "prepayment" in msg or "credits are depleted" in msg \
            or "payment required" in msg:
        return 402
    if "429" in msg or "rate limit" in msg or "ratelimit" in msg \
            or "resource_exhausted" in msg:
        return 429
    return 0


# ── public API ────────────────────────────────────────────────────────────────
def is_open(now: Optional[float] = None) -> bool:
    """True when callers should SKIP Gemini and use their non-Gemini fallback.

    Consults the free in-process state first; if that is closed, consults the DB
    flag (best-effort) so a sibling worker's trip is honoured. Never raises."""
    if _disabled():
        return False
    now = time.time() if now is None else now
    with _S.lock:
        if _S.open_now(now):
            return True
    # In-process is closed — a sibling may have tripped it. Check the DB flag,
    # and adopt its window locally so subsequent checks are free.
    until = _db_flag_open_until()
    if until and until > now:
        with _S.lock:
            if until > _S.open_until:
                _S.open_until = until
                if not _S.reason:
                    _S.reason = "credit depleted (sibling worker)"
        return True
    return False


def note_response(status_code: int, body: str = "") -> None:
    """Record a Gemini HTTP response. A 402/429 trips the breaker; anything else
    is ignored. Call this for EVERY Gemini response (success or failure). Never
    raises."""
    if _disabled():
        return
    try:
        status = int(status_code)
    except (TypeError, ValueError):
        return
    window = window_for_status(status)
    if window <= 0:
        return
    credit = _is_credit_depleted(status, body)
    if credit and window < _MIN_402 * 60.0:
        # A credit refusal that arrived under a 429/400 still earns the long window.
        window = _MIN_402 * 60.0
    reason = "credit depleted" if credit else "rate limited"
    trip(reason=reason, window_s=window, status=status)


def trip(reason: str, window_s: float, status: int = 0) -> None:
    """Open the breaker for `window_s` seconds. Logs once and writes one
    failure_events row ONLY on a real edge (closed→open or a longer window than
    the one already set). Re-confirming an already-open breaker is silent. Never
    raises."""
    if _disabled() or window_s <= 0:
        return
    now = time.time()
    new_until = now + window_s
    is_edge = False
    with _S.lock:
        was_open = _S.open_now(now)
        # An edge is: it was closed, OR this trip extends the window materially
        # (a 402 arriving while a 429's 2-minute window is open should escalate
        # to 30 minutes and be reported).
        if not was_open or new_until > _S.open_until + 1.0:
            is_edge = not was_open or (window_s >= _MIN_402 * 60.0
                                       and _S.status != 402)
            _S.open_until = new_until
            _S.reason = reason
            _S.status = status or _S.status
    # Side effects OUTSIDE the lock (I/O), only on an edge.
    if is_edge:
        minutes = int(round(window_s / 60.0))
        _log_once(reason, minutes)
        _write_flag(new_until, reason, status)
        _record_failure_event(reason, status, minutes)
    else:
        # Still refresh the DB flag so siblings keep seeing the open state, but
        # without re-logging or re-recording.
        _write_flag(new_until, reason, status)


def reset() -> None:
    """Close the breaker (in-process and DB flag). For tests and a manual
    all-clear. Never raises."""
    with _S.lock:
        _S.open_until = 0.0
        _S.reason = ""
        _S.status = 0
    _clear_flag()


def state() -> dict:
    """A snapshot for diagnostics/tests: {open, open_until, reason, status,
    seconds_left}."""
    now = time.time()
    with _S.lock:
        return {
            "open": _S.open_now(now),
            "open_until": _S.open_until,
            "reason": _S.reason,
            "status": _S.status,
            "seconds_left": max(0.0, _S.open_until - now),
        }


# ── logging (exactly once per trip edge) ───────────────────────────────────────
def _log_once(reason: str, minutes: int) -> None:
    try:
        print(f"{_LOG_PREFIX} gemini disabled {minutes}m: {reason}", flush=True)
    except Exception:
        pass


# ── failure_events row (D723), once per trip edge ──────────────────────────────
def _record_failure_event(reason: str, status: int, minutes: int) -> None:
    try:
        import failure_log
    except Exception:
        return
    try:
        # The message deliberately NAMES the credit/payment refusal so
        # failure_triage classifies it as `budget` (the credit sub-owner of the
        # external family — the ticket's external/credit). The stored triage is
        # forced to 'external' via http_status + exception_type naming the
        # provider, and the message hints ("out of credit", "payment required")
        # drive the budget sub-class.
        if status == 402 or reason == "credit depleted":
            message = (f"Gemini disabled {minutes}m: prepayment credits are "
                       f"depleted (out of credit / payment required) — "
                       f"RESOURCE_EXHAUSTED 402")
            http = 402
        else:
            message = (f"Gemini disabled {minutes}m: rate limited (429) — "
                       f"provider throttle")
            http = 429
        failure_log.record(
            service="generator",
            surface="gemini",
            error_code="gemini_credit_depleted" if http == 402
            else "gemini_rate_limited",
            message=message,
            exception_type="GeminiHTTPError",
            http_status=http,
        )
    except Exception:
        # record() already never raises, but guard the import-time path too.
        pass


# ── DB flag table (cross-process) ──────────────────────────────────────────────
# A tiny ADDITIVE single-row table. Nothing here DROPs or DELETEs user data; a
# reset() DELETEs only this breaker's own flag row. Mirrors the connection style
# of failure_log._connect (both DATABASE_URL and discrete DB_* are supported).
def _connect():
    import psycopg2  # lazy: a DB-less run still imports this module
    connect_timeout = max(1, int(round(_DB_TIMEOUT_S)))
    stmt_ms = max(1, int(_DB_TIMEOUT_S * 1000))
    options = f"-c statement_timeout={stmt_ms}"
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=connect_timeout,
                                options=options)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres-2"),
        database=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
        port=os.environ.get("DB_PORT", "5432"),
        connect_timeout=connect_timeout, options=options,
    )


_FLAG_DDL = f"""
CREATE TABLE IF NOT EXISTS {_FLAG_TABLE} (
    key         TEXT PRIMARY KEY,
    open_until  DOUBLE PRECISION NOT NULL,
    reason      TEXT,
    status      INTEGER,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _db_available() -> bool:
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("DB_HOST")
                or os.environ.get("DB_NAME"))


def _db_flag_open_until() -> float:
    """Return the DB flag's open_until epoch seconds, or 0.0 when there is no
    flag / no DB / any error. Best-effort; never raises."""
    if not _db_available():
        return 0.0
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT open_until FROM {_FLAG_TABLE} WHERE key = %s",
                        (_FLAG_KEY,))
        except Exception:
            conn.rollback()
            cur.execute(_FLAG_DDL)
            conn.commit()
            return 0.0
        row = cur.fetchone()
        cur.close()
        return float(row[0]) if row and row[0] is not None else 0.0
    except Exception:
        return 0.0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _write_flag(open_until: float, reason: str, status: int) -> None:
    """UPSERT the single breaker flag row. Best-effort; never raises."""
    if not _db_available():
        return
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        sql = f"""
            INSERT INTO {_FLAG_TABLE} (key, open_until, reason, status, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (key) DO UPDATE SET
                open_until = EXCLUDED.open_until,
                reason = EXCLUDED.reason,
                status = EXCLUDED.status,
                updated_at = now()
        """
        try:
            cur.execute(sql, (_FLAG_KEY, open_until, reason, status))
        except Exception:
            conn.rollback()
            cur.execute(_FLAG_DDL)
            conn.commit()
            cur.execute(sql, (_FLAG_KEY, open_until, reason, status))
        conn.commit()
        cur.close()
    except Exception:
        return
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _clear_flag() -> None:
    if not _db_available():
        return
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        try:
            cur.execute(f"DELETE FROM {_FLAG_TABLE} WHERE key = %s", (_FLAG_KEY,))
            conn.commit()
        except Exception:
            conn.rollback()
        cur.close()
    except Exception:
        return
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
