#!/usr/bin/env python3
"""failure_report.py — LOCAL-785 / D723: read the failure_events table.

For LEAD. Groups the recorded failures by signature over a time window and
prints, per group: count, distinct users, first/last seen, triage, ONE example
(request text + message + top stack frame) and a PRIORITY SCORE so the most
important failures sort to the top.

    python3 failure_report.py --since 24h
    python3 failure_report.py --since 7d --top 15
    python3 failure_report.py --since 1h                 # (live test window)

PRIORITY SCORE
    score = distinct_users × severity × recency_weight

  severity (how bad a single occurrence is), derived from triage:
      our_bug   → 3  (blocking — our defect; a crash/5xx)
      external  → 2  (degraded — an upstream/provider failure we must handle)
      absence   → 2  (degraded — the thing genuinely isn't there yet)
      ux        → 1  (cosmetic/guidance — the request can't be met as phrased;
                      the fix is a clearer interface, not a code bug)
      unknown   → 1  (cosmetic until a human triages it)

  recency_weight (how fresh the group is, from its LAST seen time):
      seen within 1 day  → 1.0
      seen within 7 days  → 0.6
      older              → 0.3

So a crash hitting many distinct users today outranks an old one-off, and an
honest UX refusal never outranks a real bug at equal reach. distinct_users uses
1 for a group with no identified users so a userless-but-real failure still
scores (it is never multiplied to zero).

LEAD triage override (single UPDATE, the only write this tool makes):

    python3 failure_report.py --mark <signature> <triage> [resolved_by]
    # e.g. python3 failure_report.py --mark 06f6d06ff3008097 our_bug LOCAL-790

Sets triage + triage_source='lead' (+ resolved_by when given) on every row of
that signature. <triage> must be one of our_bug|ux|external|absence|unknown.

The report path is STRICTLY READ-ONLY (a single SELECT). Connection uses the
same env as failure_log.py: DATABASE_URL if set, else DB_HOST/DB_NAME/DB_USER/
DB_PASSWORD/DB_PORT.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone

VALID_TRIAGE = ("our_bug", "ux", "external", "absence", "unknown")

# severity by triage (documented in the module docstring).
_SEVERITY = {
    "our_bug": 3,
    "external": 2,
    "absence": 2,
    "ux": 1,
    "unknown": 1,
}


def _connect():
    import psycopg2
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=5)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres-2"),
        database=os.getenv("DB_NAME", "audiotours"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "password123"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=5,
    )


_SINCE_RE = re.compile(r"^\s*(\d+)\s*([hdw])\s*$", re.IGNORECASE)


def parse_since(value: str) -> timedelta:
    """'24h' / '7d' / '1h' / '2w' -> timedelta. Hours, days, weeks."""
    m = _SINCE_RE.match(value or "")
    if not m:
        raise ValueError(
            f"--since must look like '24h', '7d', '1h' or '2w' (got {value!r})")
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    return timedelta(weeks=n)


def recency_weight(last_seen: datetime, now: datetime) -> float:
    """1.0 within a day, 0.6 within a week, else 0.3. last_seen/now tz-aware."""
    age = now - last_seen
    if age <= timedelta(days=1):
        return 1.0
    if age <= timedelta(days=7):
        return 0.6
    return 0.3


def priority_score(distinct_users: int, triage: str, last_seen: datetime,
                   now: datetime) -> float:
    severity = _SEVERITY.get((triage or "unknown"), 1)
    users = max(1, distinct_users)  # a userless real failure still scores
    return users * severity * recency_weight(last_seen, now)


def _fetch_groups(conn, since_dt):
    """One SELECT: per signature, the aggregates + the newest example row."""
    sql = """
    WITH windowed AS (
        SELECT * FROM failure_events WHERE ts >= %(since)s
    ),
    agg AS (
        SELECT
            signature,
            COUNT(*)                                   AS cnt,
            COUNT(DISTINCT user_id)                    AS distinct_users,
            MIN(ts)                                    AS first_seen,
            MAX(ts)                                    AS last_seen,
            MAX(triage)                                AS triage,
            MAX(triage_source)                         AS triage_source,
            MAX(service)                               AS service
        FROM windowed
        GROUP BY signature
    ),
    example AS (
        SELECT DISTINCT ON (signature)
            signature, error_code, message, request_text, frames,
            surface, exception_type, http_status, platform, ts
        FROM windowed
        ORDER BY signature, ts DESC
    )
    SELECT
        a.signature, a.cnt, a.distinct_users, a.first_seen, a.last_seen,
        a.triage, a.triage_source, a.service,
        e.error_code, e.message, e.request_text, e.frames, e.surface,
        e.exception_type, e.http_status, e.platform
    FROM agg a
    JOIN example e USING (signature)
    """
    cur = conn.cursor()
    cur.execute(sql, {"since": since_dt})
    rows = cur.fetchall()
    cur.close()
    cols = ["signature", "cnt", "distinct_users", "first_seen", "last_seen",
            "triage", "triage_source", "service", "error_code", "message",
            "request_text", "frames", "surface", "exception_type",
            "http_status", "platform"]
    return [dict(zip(cols, r)) for r in rows]


def _fmt_ts(dt) -> str:
    if dt is None:
        return "?"
    try:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(dt)


def _top_frame(frames) -> str:
    if not frames:
        return ""
    for line in str(frames).splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def run_report(since: str, top: int | None) -> int:
    now = datetime.now(timezone.utc)
    since_dt = now - parse_since(since)
    conn = _connect()
    try:
        groups = _fetch_groups(conn, since_dt)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    for g in groups:
        g["score"] = priority_score(
            g["distinct_users"], g["triage"], g["last_seen"], now)
    groups.sort(key=lambda g: (g["score"], g["cnt"]), reverse=True)

    total_events = sum(g["cnt"] for g in groups)
    print(f"failure_report — since {since} ({_fmt_ts(since_dt)}) — "
          f"{len(groups)} signatures, {total_events} events")
    print("=" * 78)

    shown = groups[:top] if top else groups
    if not shown:
        print("(no failures recorded in this window)")
        return 0

    for i, g in enumerate(shown, 1):
        print(f"\n#{i}  score={g['score']:.1f}  [{g['signature']}]  "
              f"{g['service'] or '?'} / {g['surface'] or '?'}")
        print(f"    count={g['cnt']}  users={g['distinct_users']}  "
              f"triage={g['triage']} ({g['triage_source']})")
        print(f"    first={_fmt_ts(g['first_seen'])}  last={_fmt_ts(g['last_seen'])}")
        _code = g["error_code"] or (f"HTTP {g['http_status']}" if g["http_status"] else "")
        _exc = f"  exc={g['exception_type']}" if g["exception_type"] else ""
        print(f"    error_code={_code or '—'}{_exc}")
        if g["message"]:
            print(f"    message: {str(g['message'])[:200]}")
        if g["request_text"]:
            print(f"    request: {str(g['request_text'])[:200]}")
        tf = _top_frame(g["frames"])
        if tf:
            print(f"    top frame: {tf[:200]}")
    return 0


def run_mark(signature: str, triage: str, resolved_by: str | None) -> int:
    if triage not in VALID_TRIAGE:
        print(f"ERROR: triage must be one of {', '.join(VALID_TRIAGE)} (got {triage!r})",
              file=sys.stderr)
        return 2
    conn = _connect()
    try:
        cur = conn.cursor()
        if resolved_by:
            cur.execute(
                "UPDATE failure_events SET triage=%s, triage_source='lead', "
                "resolved_by=%s WHERE signature=%s",
                (triage, resolved_by, signature))
        else:
            cur.execute(
                "UPDATE failure_events SET triage=%s, triage_source='lead' "
                "WHERE signature=%s",
                (triage, signature))
        n = cur.rowcount
        conn.commit()
        cur.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    print(f"Marked {n} row(s) of signature {signature} -> triage={triage}"
          + (f", resolved_by={resolved_by}" if resolved_by else ""))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Read-only failure_events report + LEAD triage mark (LOCAL-785).")
    p.add_argument("--since", default="24h",
                   help="time window: 24h | 7d | 1h | 2w (default 24h)")
    p.add_argument("--top", type=int, default=None,
                   help="show only the top N signatures by priority score")
    p.add_argument("--mark", nargs="+", metavar=("SIGNATURE TRIAGE", "RESOLVED_BY"),
                   help="LEAD override: --mark <signature> <triage> [resolved_by]")
    args = p.parse_args(argv)

    if args.mark:
        if len(args.mark) < 2 or len(args.mark) > 3:
            p.error("--mark takes <signature> <triage> [resolved_by]")
        signature = args.mark[0]
        triage = args.mark[1]
        resolved_by = args.mark[2] if len(args.mark) == 3 else None
        return run_mark(signature, triage, resolved_by)

    try:
        return run_report(args.since, args.top)
    except ValueError as e:
        p.error(str(e))


if __name__ == "__main__":
    sys.exit(main())
