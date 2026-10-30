#!/usr/bin/env python3
"""meter_report.py — total the paid-API meter's own records (LOCAL-819).

WHY THIS EXISTS
---------------
The OpenAI usage page says the mac-mini key (ends k9sA) spent $47.42 over Oct
26-30 across 28,995 requests, while the Mac meter recorded only 10,268 calls and
$17.93 — and every OpenAI row showed tokens_in/out = 0. The token=0 bug is fixed
in _meter/paid_api_meter.py (tokens_in/tokens_out are now written at the top
level). This tool is the other half: read every meter log and total it the way
the provider's usage page groups — by DAY, by SERVICE, by MODEL, and by
KEY-SUFFIX — so the metered side can be lined up against the dashboard and the
remaining gap attributed.

It makes NO paid API calls and never writes anything. It only READS the meter's
append-only JSONL logs (``meterlogs/*.jsonl``). Every isolated task container and
the shared stack append to ``~/Audioura/meterlogs`` (see SUBMISSION_LOCAL-819.md),
so globbing that directory sums ALL spend — shared listener stack plus every
task's isolated runs — in one place.

USAGE
-----
    # everything since a timestamp, grouped every way, from the default dir:
    python3 meter_report.py --since 2026-10-26

    # a precise instant (UTC) and only OpenAI rows:
    python3 meter_report.py --since 2026-10-26T04:00:00Z --kind openai

    # point at specific logs (globs allowed) instead of the default dir:
    python3 meter_report.py --since 2026-10-26 --log '~/Audioura/meterlogs/*.jsonl'

    # machine-readable:
    python3 meter_report.py --since 2026-10-26 --json

The meter writes ``ts`` in UTC (time.gmtime(), 'YYYY-MM-DDTHH:MM:SSZ'), so
``--since`` is compared as UTC. A date-only value means midnight UTC that day.
Only billed rows (status 200) count toward $ by default; pass --all-status to
include non-200 rows in the request counts (their $ is 0 either way).
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

DEFAULT_LOG_GLOB = os.path.join(
    os.path.expanduser("~"), "Audioura", "meterlogs", "*.jsonl")


def _norm_since(s):
    """Normalise a --since value to the 'YYYY-MM-DDTHH:MM:SSZ' lexical form the
    meter's ts uses, so a plain string comparison is a time comparison. A
    date-only value becomes that day's 00:00:00Z. Accepts a trailing 'Z' or a
    space instead of 'T'."""
    s = (s or "").strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1]
    if len(s) == 10:        # YYYY-MM-DD
        s += "T00:00:00"
    elif len(s) == 13:      # YYYY-MM-DDTHH
        s += ":00:00"
    elif len(s) == 16:      # YYYY-MM-DDTHH:MM
        s += ":00"
    return s + "Z"


def _norm_model(m):
    """Collapse a wire model string to the dashboard family name. OpenAI appends a
    date suffix (gpt-4o-mini-2024-07-18); the usage page groups by family, so we
    take the longest known family prefix. Non-OpenAI models pass through."""
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


def _iter_rows(paths):
    """Yield every JSON row from the given log paths. A malformed line is skipped;
    a missing file is skipped with a note on stderr."""
    for path in paths:
        if not os.path.exists(path):
            sys.stderr.write("log not found: %s\n" % path)
            continue
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def _day(ts):
    """Calendar day (UTC) from a 'YYYY-MM-DDTHH:MM:SSZ' ts, or '(no ts)'."""
    ts = str(ts or "")
    return ts[:10] if len(ts) >= 10 else "(no ts)"


def _blank():
    return {"requests": 0, "usd": 0.0, "tokens_in": 0, "tokens_out": 0}


def _add(acc, key, r, billed_only):
    a = acc[key]
    a["requests"] += 1
    if billed_only and r.get("status") != 200:
        # Still count the request, but its $ and tokens are only billed on 200.
        return
    a["usd"] += float(r.get("usd") or 0.0)
    a["tokens_in"] += int(r.get("tokens_in") or 0)
    a["tokens_out"] += int(r.get("tokens_out") or 0)


def aggregate(rows, since_z, kinds, billed_only):
    """Return (by_day, by_service, by_model, by_key, totals, n_scanned, n_kept)."""
    by_day = defaultdict(_blank)
    by_service = defaultdict(_blank)
    by_model = defaultdict(_blank)
    by_key = defaultdict(_blank)
    totals = defaultdict(_blank)
    n_scanned = n_kept = 0
    for r in rows:
        n_scanned += 1
        ts = str(r.get("ts") or "")
        if since_z and ts < since_z:
            continue
        if kinds and r.get("kind") not in kinds:
            continue
        n_kept += 1
        _add(by_day, _day(ts), r, billed_only)
        _add(by_service, str(r.get("service") or "(none)"), r, billed_only)
        _add(by_model, _norm_model(r.get("model")), r, billed_only)
        _add(by_key, str(r.get("key_suffix") or "(none)"), r, billed_only)
        _add(totals, "_", r, billed_only)
    return by_day, by_service, by_model, by_key, dict(totals)["_"], n_scanned, n_kept


def _print_group(title, acc, sort_by_name=False):
    rows = list(acc.items())
    if sort_by_name:
        rows = sorted(rows, key=lambda kv: kv[0])
    else:
        rows = sorted(rows, key=lambda kv: kv[1]["usd"], reverse=True)
    print("\n%s" % title)
    print("%-28s %10s %12s %14s %14s"
          % ("", "requests", "usd", "tokens_in", "tokens_out"))
    print("-" * 82)
    for name, a in rows:
        print("%-28s %10d %12.4f %14d %14d"
              % (str(name)[:28], a["requests"], a["usd"],
                 a["tokens_in"], a["tokens_out"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Total the paid-API meter logs by day / service / model / "
                    "key-suffix. Reads only; makes no paid calls.")
    ap.add_argument("--since", required=True,
                    help="Only rows at/after this UTC time. YYYY-MM-DD or "
                         "YYYY-MM-DDTHH:MM:SS[Z]. Date-only = 00:00:00Z that day.")
    ap.add_argument("--log", default=[DEFAULT_LOG_GLOB], action="append",
                    help="Log file or glob to read (default: "
                         "~/Audioura/meterlogs/*.jsonl). Repeatable.")
    ap.add_argument("--kind",
                    help="Comma list of kinds to include "
                         "(openai,gemini,serper,anthropic,polly,aws_translate). "
                         "Default: all.")
    ap.add_argument("--all-status", action="store_true",
                    help="Count non-200 requests in the request counts too "
                         "(their $ and tokens are 0 regardless).")
    ap.add_argument("--json", action="store_true",
                    help="Emit the aggregates as JSON instead of tables.")
    args = ap.parse_args(argv)

    # --log is 'append' with a default list; when the user passes any --log, drop
    # the leading default so only their paths are used.
    logs = args.log
    if len(logs) > 1:
        logs = logs[1:]
    paths = []
    for spec in logs:
        expanded = os.path.expanduser(spec)
        matched = sorted(glob.glob(expanded))
        paths.extend(matched or [expanded])

    since_z = _norm_since(args.since)
    kinds = ({k.strip() for k in args.kind.split(",") if k.strip()}
             if args.kind else None)
    billed_only = not args.all_status

    by_day, by_service, by_model, by_key, totals, n_scanned, n_kept = aggregate(
        _iter_rows(paths), since_z, kinds, billed_only)

    if args.json:
        out = {
            "since": since_z,
            "kinds": sorted(kinds) if kinds else "all",
            "logs": paths,
            "scanned": n_scanned,
            "kept": n_kept,
            "total": totals,
            "by_day": dict(by_day),
            "by_service": dict(by_service),
            "by_model": dict(by_model),
            "by_key_suffix": dict(by_key),
        }
        print(json.dumps(out, indent=2, default=str))
        return 0

    print("meter_report — since %s  (kinds=%s)"
          % (since_z, ",".join(sorted(kinds)) if kinds else "all"))
    print("logs: %s" % ", ".join(paths))
    print("rows scanned=%d  kept=%d  (%s)"
          % (n_scanned, n_kept, "billed only" if billed_only else "all status"))

    _print_group("BY DAY (UTC)", by_day, sort_by_name=True)
    _print_group("BY SERVICE", by_service)
    _print_group("BY MODEL", by_model)
    _print_group("BY KEY-SUFFIX", by_key)

    print("\nTOTAL   requests=%d  usd=$%.4f  tokens_in=%d  tokens_out=%d"
          % (totals["requests"], totals["usd"],
             totals["tokens_in"], totals["tokens_out"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
