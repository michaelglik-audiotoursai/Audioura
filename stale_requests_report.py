#!/usr/bin/env python3
"""stale_requests_report.py — LOCAL-846.

Read-only report of tour_requests state so LEAD can verify on the cloud that the
"tracking" rows the app never finalised are being closed out.

The defect (GCloud_Storied, 2026-10-30): the orchestrator writes TWO
tour_requests rows per generation — its own (source='orchestrator', finalised by
the orchestrator) and an app-facing tracking row (source='tracking',
tour_id='tour_'+job_id[:8]) that is only ever closed if the app sends a
tour_status_update. It frequently doesn't, so tracking rows sat at 'started' for
hours — 27 of them >1 h old at the time of the report.

This script ONLY reads. It issues SELECT statements and nothing else — no
INSERT / UPDATE / DELETE / DDL — so it is safe to run against the live cloud DB.

Output: counts grouped by (source, status) and an age histogram of the
non-terminal rows (those still 'started'), plus a focused line for the exact
population the ticket tracks: source='tracking', status='started', age > 1 h / 2 h.

Connection: resolved from standard env vars (DB_HOST, DB_PORT, DB_NAME, DB_USER,
DB_PASSWORD), defaulting to the orchestrator's own in-container defaults
(postgres-2:5432/audiotours). Override with env vars to point at the cloud, e.g.

    DB_HOST=... DB_PORT=5432 DB_NAME=audiotours DB_USER=... DB_PASSWORD=... \
        python3 stale_requests_report.py

Add --json for machine-readable output.
"""
import argparse
import json
import os
import sys


def _connect():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres-2"),
        dbname=os.getenv("DB_NAME", "audiotours"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "password123"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=10,
    )


# Every statement here is a pure SELECT. Keep it that way: this script must never
# write the live DB (LOCAL-846 constraint).
_BY_SOURCE_STATUS = """
    SELECT COALESCE(source, '(null)') AS source,
           COALESCE(status, '(null)') AS status,
           COUNT(*) AS n
      FROM tour_requests
     GROUP BY 1, 2
     ORDER BY 1, 2
"""

# Age buckets for rows that are still non-terminal (not completed/failed),
# measured against the DB clock so it is correct regardless of the caller's TZ.
_NONTERMINAL_AGE = """
    SELECT COALESCE(source, '(null)') AS source,
           COALESCE(status, '(null)') AS status,
           SUM(CASE WHEN started_at >= NOW() - INTERVAL '1 hour'  THEN 1 ELSE 0 END) AS lt_1h,
           SUM(CASE WHEN started_at <  NOW() - INTERVAL '1 hour'
                    AND started_at >= NOW() - INTERVAL '2 hours'  THEN 1 ELSE 0 END) AS h1_to_2,
           SUM(CASE WHEN started_at <  NOW() - INTERVAL '2 hours'
                    AND started_at >= NOW() - INTERVAL '24 hours' THEN 1 ELSE 0 END) AS h2_to_24,
           SUM(CASE WHEN started_at <  NOW() - INTERVAL '24 hours' THEN 1 ELSE 0 END) AS gt_24h,
           COUNT(*) AS total
      FROM tour_requests
     WHERE status NOT IN ('completed', 'failed')
     GROUP BY 1, 2
     ORDER BY 1, 2
"""

# The exact population the ticket tracks.
_TRACKING_STARTED = """
    SELECT
        SUM(CASE WHEN started_at < NOW() - INTERVAL '1 hour'  THEN 1 ELSE 0 END) AS gt_1h,
        SUM(CASE WHEN started_at < NOW() - INTERVAL '2 hours' THEN 1 ELSE 0 END) AS gt_2h,
        COUNT(*) AS total_started
      FROM tour_requests
     WHERE source = 'tracking'
       AND status = 'started'
"""


def gather(conn):
    cur = conn.cursor()
    cur.execute(_BY_SOURCE_STATUS)
    by_source_status = [
        {"source": r[0], "status": r[1], "count": int(r[2])} for r in cur.fetchall()
    ]
    cur.execute(_NONTERMINAL_AGE)
    nonterminal_age = [
        {
            "source": r[0], "status": r[1],
            "lt_1h": int(r[2]), "h1_to_2": int(r[3]),
            "h2_to_24": int(r[4]), "gt_24h": int(r[5]), "total": int(r[6]),
        }
        for r in cur.fetchall()
    ]
    cur.execute(_TRACKING_STARTED)
    row = cur.fetchone() or (0, 0, 0)
    tracking_started = {
        "gt_1h": int(row[0] or 0),
        "gt_2h": int(row[1] or 0),
        "total_started": int(row[2] or 0),
    }
    cur.close()
    return {
        "by_source_status": by_source_status,
        "nonterminal_age": nonterminal_age,
        "tracking_started": tracking_started,
    }


def _print_human(report):
    print("=" * 72)
    print("LOCAL-846 — tour_requests report (READ ONLY)")
    print("=" * 72)

    print("\nCounts by (source, status):")
    print(f"  {'source':<16}{'status':<16}{'count':>8}")
    print(f"  {'-' * 16}{'-' * 16}{'-' * 8}")
    for r in report["by_source_status"]:
        print(f"  {r['source']:<16}{r['status']:<16}{r['count']:>8}")

    print("\nNon-terminal rows by age (started_at vs DB clock):")
    hdr = (f"  {'source':<14}{'status':<12}"
           f"{'<1h':>6}{'1-2h':>7}{'2-24h':>8}{'>24h':>7}{'total':>8}")
    print(hdr)
    print(f"  {'-' * (len(hdr) - 2)}")
    for r in report["nonterminal_age"]:
        print(f"  {r['source']:<14}{r['status']:<12}"
              f"{r['lt_1h']:>6}{r['h1_to_2']:>7}{r['h2_to_24']:>8}"
              f"{r['gt_24h']:>7}{r['total']:>8}")

    ts = report["tracking_started"]
    print("\nTicket population — source='tracking', status='started':")
    print(f"  total 'started' : {ts['total_started']}")
    print(f"  > 1 h old       : {ts['gt_1h']}")
    print(f"  > 2 h old       : {ts['gt_2h']}  (the sweep target)")
    print("=" * 72)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only tour_requests staleness report (LOCAL-846)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    try:
        conn = _connect()
    except Exception as e:
        print(f"ERROR: could not connect to the database: {e}", file=sys.stderr)
        return 2
    try:
        report = gather(conn)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
