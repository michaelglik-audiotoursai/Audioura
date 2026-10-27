#!/usr/bin/env python3
"""failure_log.py — LOCAL-785 / D723: the ONE server-side failure recorder.

Michael (D723): "Record all failures so later we can identify what happened. If
it's our fault we fix it; if it's the user's mistake we make the interface more
intuitive."

`record(...)` writes one row to the failure_events table (migration 054). It is
wired into every server failure path — orchestrator job failure + refusal,
generator clean-fail evidence, translation / tour-id-resolution / map-delivery
errors, and a Flask errorhandler(Exception) in each service.

HARD CONTRACT (the reason this module exists and is tested red-first):

  * record() NEVER raises. A failure in the failure recorder must never turn a
    handled failure into a crash, or a 500 into a worse 500. Every path is
    wrapped; the worst case is a line on stdout.
  * The DB write has a 1-second timeout (connect + statement). A down or slow
    DB must not stall the caller.
  * If the DB is unreachable (or the write fails for any reason), the event is
    still emitted as a single JSON line on stdout, prefixed FAILURE_EVENT, so
    the raw container logs keep the record (exactly how 445/446 were found).

Both DB connection styles in the codebase are supported:
  * discrete DB_* env (orchestrator/generator/tour-id-resolution/map-delivery),
  * DATABASE_URL (user-api / user-tracking).

The signature groups "the same failure" across ids/numbers/quotes:
    sha1(service + '|' + error_code + '|' + exception_type + '|' + normalised(message))[:16]
where normalise() strips digits, UUID/hex ids and quoted strings so
"tour 445 failed" and "tour 446 failed" share one signature.

The module is import-safe with NO hard dependency on psycopg2 at import time
(it is imported lazily inside the DB path), so a service that lacks a DB can
still import and call record() — it simply falls back to stdout.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import traceback as _traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

__all__ = ["record", "compute_signature", "auto_triage", "normalise_message"]

# ---------------------------------------------------------------------------
# Tunables (env-overridable; safe defaults).
# ---------------------------------------------------------------------------

# DB connect + statement timeout, seconds. The contract is "never stall the
# caller" — 1s is generous for a local write and bounds a cloud outage.
_DB_TIMEOUT_S = float(os.getenv("FAILURE_LOG_DB_TIMEOUT", "1") or "1")

# Column caps so one giant message/stack can never blow up a row or a log line.
_MSG_CAP = 4000
_REQUEST_CAP = 4000
_FRAMES_CAP = 4000
_MAX_FRAMES = 8  # top N stack frames kept


# ---------------------------------------------------------------------------
# Signature.
# ---------------------------------------------------------------------------

_DIGITS_RE = re.compile(r"\d+")
# A hex/uuid-ish id token (8+ hex chars, optional dashes) — strip before digits.
_HEXID_RE = re.compile(r"\b[0-9a-fA-F]{8}(?:-?[0-9a-fA-F]{4,}){0,4}\b")
_QUOTED_RE = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")
_WS_RE = re.compile(r"\s+")


def normalise_message(message: Optional[str]) -> str:
    """Strip the variable parts of a message so like failures hash alike.

    Removes quoted strings, hex/uuid ids and digit runs, lowercases, and
    collapses whitespace. 'Tour 445 ("Boston") failed' and 'Tour 446 ("Paris")
    failed' both normalise to 'tour failed'.
    """
    if not message:
        return ""
    s = str(message)
    s = _QUOTED_RE.sub(" ", s)   # drop quoted literals first (may contain ids)
    s = _HEXID_RE.sub(" ", s)    # then hex/uuid ids
    s = _DIGITS_RE.sub(" ", s)   # then any remaining digit runs
    s = s.lower()
    s = _WS_RE.sub(" ", s).strip()
    return s


def compute_signature(service: Optional[str], error_code: Optional[str],
                      exception_type: Optional[str], message: Optional[str]) -> str:
    """The stable 16-hex-char group key for a failure.

    sha1(service|error_code|exception_type|normalised message)[:16]. Deterministic
    and stable across ids/numbers/quotes (via normalise_message), so the report
    counts the same failure as one group.
    """
    basis = "|".join([
        (service or "").strip().lower(),
        (error_code or "").strip().lower(),
        (exception_type or "").strip(),
        normalise_message(message),
    ])
    return hashlib.sha1(basis.encode("utf-8", "replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Auto-triage — one function, one documented rules table.
# ---------------------------------------------------------------------------
#
# triage answers "whose fault is it?" so LEAD can act:
#   our_bug  — a crash/5xx/timeout/our-code defect. WE fix it.
#   ux       — the user asked for something impossible-as-phrased; the honest,
#              actionable refusals (venue has no content, closed, no matches in
#              area, unclassifiable). FIX = make the interface guide them.
#   external — an upstream/provider failure (model API, Polly, maps) or a
#              network error we don't own.
#   absence  — the thing genuinely does not exist / isn't researched yet
#              (exhibition_not_found, by_reference_no_material).
#   unknown  — nothing matched; a human should look.
#
# The rules are ordered: the FIRST matching rule wins. error_code is the
# strongest signal (it is the LOCAL-774 contract); exception_type and
# http_status back it up when there is no error_code.

# error_code -> triage (the LOCAL-774 stable codes, actionable_failure.ERROR_CODES).
_ERROR_CODE_TRIAGE = {
    # The user's request can't be satisfied as phrased — guide them (UX).
    "venue_no_verifiable_content": "ux",
    "venue_misread": "ux",
    "stops_not_colocated": "ux",
    "request_unclassifiable": "ux",
    "no_matching_places_in_area": "ux",
    "content_quality_insufficient": "ux",
    "factual_integrity": "ux",
    "venue_closed": "ux",
    "exhibition_closed": "ux",
    # The thing isn't there / isn't researched yet (absence).
    "exhibition_not_found": "absence",
    "by_reference_no_material": "absence",
    # Our generation pipeline could not produce a tour — our bug to chase.
    "generation_failed": "our_bug",
    # A paywall/entitlement the CREATOR hit is a bug (a creator should never be
    # charged for their own tour) — see map-delivery 402-for-creator note.
    "purchase_required_for_creator": "our_bug",
}

# exception_type substrings -> triage (used when error_code is absent/unknown).
_EXTERNAL_EXC_HINTS = (
    "timeout", "connectionerror", "connectionrefused", "socket",
    "readtimeout", "connecttimeout", "sslerror", "httperror",
    "clientexception", "oserror", "gaierror",
)


def auto_triage(error_code: Optional[str], exception_type: Optional[str],
                http_status: Optional[int]) -> str:
    """Return the seeded triage for a failure. First matching rule wins.

    Documented rules table (also reproduced in SUBMISSION_LOCAL-785.md):
      1. a known error_code maps via _ERROR_CODE_TRIAGE;
      2. else a 5xx http_status is our_bug (our server erred);
      3. else a network/timeout-ish exception_type is external;
      4. else any other exception_type (a real crash) is our_bug;
      5. else unknown.
    """
    ec = (error_code or "").strip().lower()
    if ec in _ERROR_CODE_TRIAGE:
        return _ERROR_CODE_TRIAGE[ec]

    try:
        status = int(http_status) if http_status is not None else None
    except (TypeError, ValueError):
        status = None
    if status is not None and 500 <= status <= 599:
        return "our_bug"

    et = (exception_type or "").strip().lower()
    if et:
        if any(h in et for h in _EXTERNAL_EXC_HINTS):
            return "external"
        # A concrete exception type that is not a known external error is a
        # crash in our code until proven otherwise.
        return "our_bug"

    return "unknown"


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _frames_from_exc(exc: Optional[BaseException], frames: Optional[str]) -> str:
    """Top _MAX_FRAMES stack frames as text. Prefer an explicit `frames` string;
    else derive from the exception's traceback; else the current traceback."""
    if frames:
        return str(frames)[:_FRAMES_CAP]
    tb = None
    if exc is not None and getattr(exc, "__traceback__", None) is not None:
        tb = _traceback.format_exception(type(exc), exc, exc.__traceback__)
    else:
        # Only meaningful if called inside an `except`; harmless otherwise.
        cur = sys.exc_info()
        if cur and cur[0] is not None:
            tb = _traceback.format_exception(*cur)
    if not tb:
        return ""
    # Keep the LAST _MAX_FRAMES frame lines (closest to the error) + the final
    # exception line, which is what a human reads first.
    text = "".join(tb)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    kept = lines[-(_MAX_FRAMES * 2 + 1):]  # ~2 lines per frame + the exc line
    return "\n".join(kept)[:_FRAMES_CAP]


def _cap(value: Optional[str], cap: int) -> Optional[str]:
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= cap else s[:cap]


def _connect(timeout_s: float):
    """Open a psycopg2 connection with a bounded connect + statement timeout,
    supporting BOTH connection styles. Returns a connection or raises."""
    import psycopg2  # lazy: a DB-less service can still import this module

    connect_timeout = max(1, int(round(timeout_s)))
    # statement_timeout is milliseconds; applied via options so it binds the
    # INSERT too, not just the connect.
    stmt_ms = max(1, int(timeout_s * 1000))
    options = f"-c statement_timeout={stmt_ms}"

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(
            database_url, connect_timeout=connect_timeout, options=options
        )
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres-2"),
        database=os.getenv("DB_NAME", "audiotours"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "password123"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=connect_timeout,
        options=options,
    )


_SELF_HEAL_DDL = """
CREATE TABLE IF NOT EXISTS failure_events (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    user_id         TEXT,
    app_version     TEXT,
    platform        TEXT,
    track           TEXT,
    surface         TEXT,
    error_code      TEXT,
    message         TEXT,
    request_text    TEXT,
    tour_id         TEXT,
    job_id          TEXT,
    exception_type  TEXT,
    frames          TEXT,
    http_status     INTEGER,
    service         TEXT,
    signature       CHAR(16)     NOT NULL,
    triage          TEXT         NOT NULL DEFAULT 'unknown',
    triage_source   TEXT         NOT NULL DEFAULT 'auto',
    resolved_by     TEXT
);
"""

_INSERT_SQL = """
INSERT INTO failure_events
    (ts, user_id, app_version, platform, track, surface, error_code, message,
     request_text, tour_id, job_id, exception_type, frames, http_status,
     service, signature, triage, triage_source)
VALUES
    (%(ts)s, %(user_id)s, %(app_version)s, %(platform)s, %(track)s, %(surface)s,
     %(error_code)s, %(message)s, %(request_text)s, %(tour_id)s, %(job_id)s,
     %(exception_type)s, %(frames)s, %(http_status)s, %(service)s,
     %(signature)s, %(triage)s, %(triage_source)s)
"""


def _build_row(service, surface, error_code, message, exception_type, frames,
               http_status, user_id, app_version, platform, track,
               request_text, tour_id, job_id, exc) -> Dict[str, Any]:
    exception_type = exception_type or (type(exc).__name__ if exc is not None else None)
    message = message if message is not None else (str(exc) if exc is not None else None)
    frames_text = _frames_from_exc(exc, frames)
    try:
        status_int = int(http_status) if http_status is not None else None
    except (TypeError, ValueError):
        status_int = None
    signature = compute_signature(service, error_code, exception_type, message)
    triage = auto_triage(error_code, exception_type, status_int)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_id": _cap(user_id, 255),
        "app_version": _cap(app_version, 64),
        "platform": _cap(platform, 32),
        "track": _cap(track, 32),
        "surface": _cap(surface, 64),
        "error_code": _cap(error_code, 128),
        "message": _cap(message, _MSG_CAP),
        "request_text": _cap(request_text, _REQUEST_CAP),
        "tour_id": _cap(None if tour_id is None else str(tour_id), 64),
        "job_id": _cap(None if job_id is None else str(job_id), 128),
        "exception_type": _cap(exception_type, 128),
        "frames": _cap(frames_text, _FRAMES_CAP),
        "http_status": status_int,
        "service": _cap(service, 64),
        "signature": signature,
        "triage": triage,
        "triage_source": "auto",
    }


def _emit_stdout(row: Dict[str, Any], reason: str = "") -> None:
    """Last-resort durable record: one JSON line on stdout. This is how the
    445/446 silent failures were recovered, so it must always run when the DB
    write did not."""
    try:
        payload = dict(row)
        if reason:
            payload["_fallback_reason"] = reason
        line = "FAILURE_EVENT " + json.dumps(payload, default=str, ensure_ascii=False)
        print(line, flush=True)
    except Exception:
        # Even the fallback must never raise. A bare marker is better than a crash.
        try:
            print("FAILURE_EVENT {\"signature\": \"%s\"}" % row.get("signature", ""),
                  flush=True)
        except Exception:
            pass


def record(*, service: str, surface: Optional[str] = None,
           error_code: Optional[str] = None, message: Optional[str] = None,
           exception_type: Optional[str] = None, frames: Optional[str] = None,
           http_status: Optional[int] = None, user_id: Optional[str] = None,
           app_version: Optional[str] = None, platform: str = "server",
           track: Optional[str] = None, request_text: Optional[str] = None,
           tour_id: Optional[Any] = None, job_id: Optional[Any] = None,
           exc: Optional[BaseException] = None) -> str:
    """Record one failure. Returns the computed signature (always), writes a row
    to failure_events (best-effort, 1s timeout) and, if that write does not
    land, emits the event as a JSON line on stdout.

    NEVER raises. Every argument is keyword-only so call sites read clearly and
    never pass a value to the wrong column. `exc` (an exception object) fills in
    exception_type / message / frames when not given explicitly.
    """
    # 1. Build the row. This itself is wrapped — a bad argument must not raise.
    try:
        row = _build_row(service, surface, error_code, message, exception_type,
                         frames, http_status, user_id, app_version, platform,
                         track, request_text, tour_id, job_id, exc)
    except Exception:
        try:
            sig = compute_signature(service, error_code, exception_type, message)
        except Exception:
            sig = ""
        try:
            print("FAILURE_EVENT " + json.dumps(
                {"service": service, "signature": sig,
                 "_fallback_reason": "build_row_failed"}, default=str),
                flush=True)
        except Exception:
            pass
        return sig

    signature = row["signature"]

    # 2. Try the DB write, bounded by the timeout. Any failure -> stdout.
    conn = None
    try:
        conn = _connect(_DB_TIMEOUT_S)
        cur = conn.cursor()
        try:
            cur.execute(_INSERT_SQL, row)
        except Exception:
            # The table may be missing on a DB that never ran migration 054.
            # Self-heal once, then retry the insert.
            conn.rollback()
            cur.execute(_SELF_HEAL_DDL)
            conn.commit()
            cur.execute(_INSERT_SQL, row)
        conn.commit()
        cur.close()
        return signature
    except Exception as db_err:
        _emit_stdout(row, reason=f"db_unavailable: {type(db_err).__name__}")
        return signature
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
