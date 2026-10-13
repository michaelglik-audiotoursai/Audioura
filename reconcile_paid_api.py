#!/usr/bin/env python3
"""reconcile_paid_api.py — compare a day's METERED paid-API usage against the
numbers Michael reads off the OpenAI (or Google) dashboard, and print the gap.

[LOCAL-678] This script makes NO paid API calls. It only READS the meter's own
record (the paid_api_calls DB table, or the jsonl log as a fallback) and a small
"expected" file you paste the dashboard numbers into. Its whole job is to answer:
"the dashboard says N requests / $X for gpt-4o-mini on this day — how many did the
meter actually record, and what is the gap?"

USAGE
-----
    # metered side, grouped by model, for one UTC day:
    python3 reconcile_paid_api.py --date 2026-10-11

    # with a pasted-dashboard file to compute the gap per model:
    python3 reconcile_paid_api.py --date 2026-10-11 --expected dashboard_2026-10-11.json

    # read the jsonl log instead of the DB (host runs that had no DB mount):
    python3 reconcile_paid_api.py --date 2026-10-11 --log /meterlogs/paid_api_calls.jsonl

The --expected file is JSON you fill in from the dashboard, e.g.:

    {
      "date": "2026-10-11",
      "tz": "UTC",
      "models": {
        "gpt-4o-mini":  {"requests": 1586, "usd": 2.11},
        "gpt-4o":       {"requests": 442,  "usd": 1.90},
        "gpt-4.1":      {"requests": 404},
        "gpt-4.1-mini": {"requests": 105}
      },
      "total": {"requests": 9400, "usd": 26.80}
    }

Only `requests` is required per model; `usd` is optional. A model you don't list
is still shown (metered side) with an empty expected column.

The day boundary matches how the meter writes `ts` (UTC, from time.gmtime()).
Pass --tz to interpret the date in another timezone when reading the DB.
"""
import argparse
import json
import os
import sys
from collections import defaultdict


def _norm_model(m):
    """Collapse a wire model string to the dashboard family name. OpenAI appends a
    date suffix (gpt-4o-mini-2024-07-18); the dashboard groups by the family, so
    we take the longest known family prefix."""
    m = (m or "").strip()
    if not m:
        return "(none)"
    families = [
        "gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1",
        "gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo",
        "text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002",
    ]
    best = None
    for f in families:
        if m.startswith(f) and (best is None or len(f) > len(best)):
            best = f
    return best or m


def _from_db(date_str, tz, kinds):
    """Return list of (model, usd, status) rows for the given day. Raises on DB
    error so the caller can fall back to the log."""
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(url, connect_timeout=5) if url else psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        dbname=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
        port=os.environ.get("DB_PORT", "5432"), connect_timeout=5)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT model, usd, status, kind FROM paid_api_calls "
                "WHERE (ts AT TIME ZONE %s)::date = %s::date",
                (tz, date_str))
            rows = cur.fetchall()
    finally:
        try: conn.close()
        except Exception: pass
    return [(r[0], r[1], r[2], r[3]) for r in rows
            if (not kinds or r[3] in kinds)]


def _from_log(path, date_str, kinds):
    """Return list of (model, usd, status, kind) rows from the jsonl log for the
    given UTC day (ts starts with 'YYYY-MM-DD')."""
    rows = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not str(r.get("ts", "")).startswith(date_str):
                    continue
                if kinds and r.get("kind") not in kinds:
                    continue
                rows.append((r.get("model"), r.get("usd"), r.get("status"), r.get("kind")))
    except FileNotFoundError:
        sys.stderr.write("log not found: %s\n" % path)
    return rows


def _aggregate(rows, billed_only):
    """model -> {'requests': n, 'usd': sum}. billed_only keeps status==200."""
    agg = defaultdict(lambda: {"requests": 0, "usd": 0.0})
    for model, usd, status, _kind in rows:
        if billed_only and status != 200:
            continue
        fam = _norm_model(model)
        agg[fam]["requests"] += 1
        agg[fam]["usd"] += float(usd or 0.0)
    return agg


def main():
    ap = argparse.ArgumentParser(description="Reconcile metered paid-API usage vs dashboard. No paid calls.")
    ap.add_argument("--date", required=True, help="Day to reconcile, YYYY-MM-DD")
    ap.add_argument("--tz", default="UTC", help="Timezone for the DB day boundary (default UTC, matches how the meter writes ts)")
    ap.add_argument("--expected", help="JSON file of dashboard numbers to compute the gap")
    ap.add_argument("--log", help="Read the jsonl meter log instead of the DB")
    ap.add_argument("--kind", default="openai", help="Comma list of kinds to include (openai,gemini,serper,...); default openai")
    ap.add_argument("--all-status", action="store_true", help="Count all requests, not only billed (status 200)")
    args = ap.parse_args()

    kinds = {k.strip() for k in args.kind.split(",") if k.strip()} or None
    billed_only = not args.all_status

    rows, source = None, None
    if args.log:
        rows = _from_log(args.log, args.date, kinds)
        source = "log:%s" % args.log
    else:
        try:
            rows = _from_db(args.date, args.tz, kinds)
            source = "db(paid_api_calls)"
        except Exception as e:
            fallback = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")
            sys.stderr.write("DB read failed (%s); falling back to log %s\n" % (str(e)[:150], fallback))
            rows = _from_log(fallback, args.date, kinds)
            source = "log:%s (db fallback)" % fallback

    metered = _aggregate(rows, billed_only)

    expected = {}
    exp_total = None
    if args.expected:
        with open(args.expected) as fh:
            ex = json.load(fh)
        expected = {_norm_model(k): v for k, v in (ex.get("models") or {}).items()}
        exp_total = ex.get("total")

    models = sorted(set(metered) | set(expected))
    print("Reconciliation for %s  (kinds=%s, %s, source=%s)"
          % (args.date, ",".join(sorted(kinds)) if kinds else "all",
             "billed only" if billed_only else "all status", source))
    print("%-26s %10s %12s %10s %12s %10s"
          % ("model", "metered_req", "metered_usd", "dash_req", "dash_usd", "gap_req"))
    print("-" * 88)
    tot_m_req = tot_m_usd = 0
    tot_e_req = 0
    for fam in models:
        m = metered.get(fam, {"requests": 0, "usd": 0.0})
        e = expected.get(fam, {})
        e_req = e.get("requests")
        e_usd = e.get("usd")
        gap = (e_req - m["requests"]) if isinstance(e_req, (int, float)) else None
        tot_m_req += m["requests"]
        tot_m_usd += m["usd"]
        if isinstance(e_req, (int, float)):
            tot_e_req += e_req
        print("%-26s %10d %12.4f %10s %12s %10s"
              % (fam, m["requests"], m["usd"],
                 e_req if e_req is not None else "-",
                 ("%.2f" % e_usd) if isinstance(e_usd, (int, float)) else "-",
                 gap if gap is not None else "-"))
    print("-" * 88)
    print("%-26s %10d %12.4f %10s %12s %10s"
          % ("TOTAL (listed)", tot_m_req, tot_m_usd,
             tot_e_req if expected else "-", "-",
             (tot_e_req - tot_m_req) if expected else "-"))
    if exp_total:
        dreq = exp_total.get("requests")
        dusd = exp_total.get("usd")
        print("\nDashboard day total: requests=%s usd=%s" % (dreq, dusd))
        if isinstance(dreq, (int, float)):
            print("UNMETERED REQUEST GAP (dashboard total - metered listed): %d"
                  % (dreq - tot_m_req))
        if isinstance(dusd, (int, float)):
            print("UNMETERED $ GAP (dashboard total - metered listed): $%.2f"
                  % (dusd - tot_m_usd))


if __name__ == "__main__":
    main()
