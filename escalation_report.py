#!/usr/bin/env python3
"""escalation_report.py — LOCAL-784 / D722: LEAD's read-only escalation report.

Reads the `lookup_escalations` table (migration 055) and prints, for a time
window, the escalation events grouped by (kind, category, tier_found) with
counts, total/avg cost, and a few concrete examples per group. For LEAD's hourly
tick: it answers "where did the cheap tools miss, and what rescued it — Serper
(tier b), grounded Gemini (tier c), or was it a genuine absence (none)?".

This script is STRICTLY READ-ONLY: it issues SELECTs only, never a write of any
kind. It also prints the current learned-routing table (lookup_routing) so LEAD
can see which (category, region) cells have been promoted off the cheap tier, and
which rows could be deleted to revert them (every routing row is reversible).

USAGE
-----
    python3 escalation_report.py                 # last 24h (default)
    python3 escalation_report.py --since 48h
    python3 escalation_report.py --since 7d --examples 5
    python3 escalation_report.py --tier none     # only genuine absences
    python3 escalation_report.py --kind dining
    python3 escalation_report.py --json          # machine-readable

Connection: DATABASE_URL if set, else the discrete DB_* env (DB_HOST/DB_NAME/
DB_USER/DB_PASSWORD/DB_PORT), matching every other tool in the repo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone


def _parse_since(s: str) -> timedelta:
    """Parse a window like '24h', '48h', '7d', '90m' into a timedelta. Defaults
    to 24h on anything unrecognised."""
    s = (s or "").strip().lower()
    if not s:
        return timedelta(hours=24)
    try:
        if s.endswith("h"):
            return timedelta(hours=float(s[:-1]))
        if s.endswith("d"):
            return timedelta(days=float(s[:-1]))
        if s.endswith("m"):
            return timedelta(minutes=float(s[:-1]))
        # Bare number = hours.
        return timedelta(hours=float(s))
    except ValueError:
        return timedelta(hours=24)


def _connect():
    """Open a read-only-intent psycopg2 connection (dual connection style)."""
    import psycopg2
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=5)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres-2"),
        database=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
        port=os.environ.get("DB_PORT", "5432"),
        connect_timeout=5)


# Tier labels for the human report.
_TIER_LABEL = {
    "a": "tier a (cheap path)",
    "b": "tier b (Serper Places)",
    "c": "tier c (grounded Gemini, re-verified)",
    "none": "NONE — genuine absence (honest refusal)",
}


def fetch(since: timedelta, kind_filter=None, tier_filter=None, examples=3):
    """Return (groups, routing, totals). groups is a list of dicts, one per
    (kind, category, tier_found), each with count, cost and example rows.
    READ-ONLY — SELECT statements only."""
    cutoff = datetime.now(timezone.utc) - since
    conn = _connect()
    try:
        # Make the session read-only so this tool can never mutate anything, even
        # by accident or via a future edit. A failure to set it is non-fatal
        # (older PG honours it; the queries below are SELECT-only regardless).
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

        where = ["ts >= %s"]
        params = [cutoff]
        if kind_filter:
            where.append("kind = %s")
            params.append(kind_filter)
        if tier_filter:
            where.append("tier_found = %s")
            params.append(tier_filter)
        where_sql = " AND ".join(where)

        with conn.cursor() as cur:
            # Grouped counts + cost.
            cur.execute(
                f"SELECT kind, category, tier_found, COUNT(*), "
                f"COALESCE(SUM(cost_usd),0), COALESCE(AVG(cost_usd),0) "
                f"FROM lookup_escalations WHERE {where_sql} "
                f"GROUP BY kind, category, tier_found "
                f"ORDER BY COUNT(*) DESC, kind, category, tier_found",
                params)
            grouped = cur.fetchall()

            groups = []
            for kind, category, tier, count, total_cost, avg_cost in grouped:
                # A few concrete, newest examples for this group.
                ex_params = list(params) + [kind, category, tier, int(examples)]
                # kind/category can be NULL — match with IS NOT DISTINCT FROM.
                cur.execute(
                    f"SELECT ts, request, scope, results_by_tier, cost_usd "
                    f"FROM lookup_escalations WHERE {where_sql} "
                    f"AND kind IS NOT DISTINCT FROM %s "
                    f"AND category IS NOT DISTINCT FROM %s "
                    f"AND tier_found = %s "
                    f"ORDER BY ts DESC LIMIT %s",
                    ex_params)
                examples_rows = []
                for ts, request, scope, rbt, cost in cur.fetchall():
                    examples_rows.append({
                        "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                        "request": request,
                        "scope": scope,
                        "results_by_tier": (rbt if isinstance(rbt, dict)
                                            else _safe_json(rbt)),
                        "cost_usd": float(cost or 0.0),
                    })
                groups.append({
                    "kind": kind,
                    "category": category,
                    "tier_found": tier,
                    "count": int(count),
                    "total_cost_usd": float(total_cost or 0.0),
                    "avg_cost_usd": float(avg_cost or 0.0),
                    "examples": examples_rows,
                })

            # Overall totals.
            cur.execute(
                f"SELECT COUNT(*), COALESCE(SUM(cost_usd),0), "
                f"COUNT(*) FILTER (WHERE tier_found='b'), "
                f"COUNT(*) FILTER (WHERE tier_found='c'), "
                f"COUNT(*) FILTER (WHERE tier_found='none') "
                f"FROM lookup_escalations WHERE {where_sql}",
                params)
            tot = cur.fetchone()
            totals = {
                "events": int(tot[0] or 0),
                "total_cost_usd": float(tot[1] or 0.0),
                "rescued_tier_b": int(tot[2] or 0),
                "rescued_tier_c": int(tot[3] or 0),
                "absences_none": int(tot[4] or 0),
            }

            # Learned routing snapshot (the reversible levers).
            cur.execute(
                "SELECT category, region_key, start_tier, misses_7d, updated_at "
                "FROM lookup_routing ORDER BY misses_7d DESC, updated_at DESC "
                "LIMIT 50")
            routing = [{
                "category": c, "region_key": rk, "start_tier": st,
                "misses_7d": int(m or 0),
                "updated_at": (u.isoformat() if hasattr(u, "isoformat") else str(u)),
            } for c, rk, st, m, u in cur.fetchall()]

        return groups, routing, totals
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _safe_json(v):
    try:
        return json.loads(v) if isinstance(v, (str, bytes)) else (v or {})
    except Exception:
        return {}


def _print_text(since_text, groups, routing, totals):
    print("=" * 74)
    print(f"[D722] Escalation report — window: last {since_text}")
    print("=" * 74)
    print(f"Escalation events: {totals['events']}   "
          f"(tier b rescued {totals['rescued_tier_b']}, "
          f"tier c rescued {totals['rescued_tier_c']}, "
          f"genuine absences {totals['absences_none']})")
    print(f"Total escalation spend: ${totals['total_cost_usd']:.4f}")
    print()
    if not groups:
        print("No escalation events in the window. Either the cheap tier is "
              "satisfying every request (tier-a hits write no row), or there was "
              "no business/dining/by-reference traffic.")
    for g in groups:
        tier = g["tier_found"]
        print("-" * 74)
        print(f"{_TIER_LABEL.get(tier, tier)}  |  kind={g['kind'] or '-'}  "
              f"category={g['category'] or '-'}")
        print(f"  events: {g['count']}   total ${g['total_cost_usd']:.4f}   "
              f"avg ${g['avg_cost_usd']:.4f}")
        for ex in g["examples"]:
            rbt = ex["results_by_tier"] or {}
            a = ", ".join(rbt.get("a") or []) or "—"
            b = ", ".join(rbt.get("b") or []) or "—"
            c = ", ".join(rbt.get("c") or []) or "—"
            print(f"    · {ex['ts']}  scope={ex['scope'] or '-'!r}  "
                  f"req={(ex['request'] or '')[:60]!r}")
            print(f"        a:[{a}]  b:[{b}]  c:[{c}]  (${ex['cost_usd']:.4f})")
    print()
    print("=" * 74)
    print("Learned routing (lookup_routing) — reversible: DELETE a row to revert "
          "that cell to start-at-tier-a.")
    print("=" * 74)
    if not routing:
        print("  (no routing rows — every lookup still starts at the cheap tier)")
    else:
        print(f"  {'category':<22} {'region_key':<12} {'start':<6} {'misses_7d':<10} updated_at")
        for r in routing:
            promoted = "*" if (r["misses_7d"] >= 3 and r["start_tier"] in ("b", "c")) else " "
            print(f" {promoted}{r['category'][:21]:<21} {r['region_key']:<12} "
                  f"{r['start_tier']:<6} {r['misses_7d']:<10} {r['updated_at']}")
        print("  (* = promoted: the ladder starts at the dearer tier for this cell)")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="LOCAL-784/D722 read-only escalation report (lookup_escalations).")
    ap.add_argument("--since", default="24h",
                    help="window: 24h (default), 48h, 7d, 90m, or a bare number of hours.")
    ap.add_argument("--kind", default=None,
                    help="filter: dining | business | by_reference")
    ap.add_argument("--tier", default=None, choices=["a", "b", "c", "none"],
                    help="filter to one tier_found value (e.g. 'none' for genuine absences).")
    ap.add_argument("--examples", type=int, default=3,
                    help="example rows per group (default 3).")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of the text report.")
    args = ap.parse_args(argv)

    since = _parse_since(args.since)
    try:
        groups, routing, totals = fetch(since, kind_filter=args.kind,
                                        tier_filter=args.tier,
                                        examples=max(0, args.examples))
    except Exception as e:
        print(f"[D722] escalation_report: could not read lookup_escalations: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "since": args.since, "totals": totals,
            "groups": groups, "routing": routing,
        }, indent=2, default=str))
    else:
        _print_text(args.since, groups, routing, totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
