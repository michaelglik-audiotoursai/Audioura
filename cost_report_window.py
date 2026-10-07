#!/usr/bin/env python3
"""cost_report_window.py — "where did the money go?" in one command (LOCAL-613).

Reads the shared ``cost_ledger`` over a time window and prints two breakdowns:

  * BY PROVIDER — openai, gemini_grounding, gemini_tokens, serper, preflight, tts,
    other — summed from each row's ``breakdown`` JSONB (the LOCAL-609 fields the
    LOCAL-613 meter writes). Rows with no provider breakdown (older live rows)
    fall into ``unattributed`` so the dollars still reconcile to the row totals.
  * BY USER — every ``user_id``, split into LIVE users and ``TEST-*`` test runs,
    with per-group subtotals. This is what answers Michael's question: of the $14
    burned overnight, how much was live users vs isolated Kiro test runs.

Why it exists
=============
On 2026-10-06 Gemini went from $14.06 to $0 in ~11 hours, but the ledger held
only 14 live ``tour_generate`` rows ($1.05). The rest was isolated test runs that
wrote nothing. With LOCAL-613 those runs now write ``TEST-*`` rows, and this
command sums any window so the spend is reconstructable from one place.

Usage
=====
    python3 cost_report_window.py --from 2026-10-06T20:56Z --to 2026-10-07T04:29Z
    python3 cost_report_window.py --from "2026-10-06 20:56" --to "2026-10-07 04:29" --json

Timestamps accept ISO 8601 (``2026-10-06T20:56Z`` / ``...+00:00``) or
``YYYY-MM-DD HH:MM`` / ``YYYY-MM-DD``. A naive timestamp (no zone) is read as UTC.
The window is inclusive of ``--from`` and exclusive of ``--to`` (``created_at >=
from AND < to``). No DELETE, no mutation — this command only reads.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2

# Provider buckets, in report order. Mirrors tests/live_run_meter.BREAKDOWN_FIELDS
# plus tts (a real cost line present on some live rows) and catch-alls.
PROVIDER_ORDER = (
    "openai",
    "gemini_grounding",
    "gemini_tokens",
    "serper",
    "preflight",
    "tts",
    "other",
    "unattributed",
)


def _get_db_url():
    """Resolve the ledger database URL the same way cost_meter does, so the
    report reads exactly the ledger the meter writes."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return db_url
    host = os.environ.get("DB_HOST", "postgres-2")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ.get("DB_NAME", "audiotours")
    user = os.environ.get("DB_USER", "admin")
    password = os.environ.get("DB_PASSWORD", "password123")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def parse_ts(raw):
    """Parse a window bound into a timezone-aware UTC datetime.

    Accepts ISO 8601 (with 'Z' or offset), 'YYYY-MM-DD HH:MM[:SS]', or
    'YYYY-MM-DD'. Naive values are interpreted as UTC."""
    s = str(raw).strip()
    # Normalise a trailing 'Z' to an explicit +00:00 for fromisoformat.
    iso = s.replace("Z", "+00:00").replace("z", "+00:00")
    dt = None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        raise argparse.ArgumentTypeError(
            f"could not parse timestamp {raw!r} — use ISO 8601 "
            f"(2026-10-06T20:56Z) or 'YYYY-MM-DD HH:MM'")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_dict(breakdown):
    """Coerce a ledger ``breakdown`` cell (dict, JSON string, or None) to a dict."""
    if breakdown is None:
        return {}
    if isinstance(breakdown, dict):
        return breakdown
    try:
        v = json.loads(breakdown)
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def _provider_amounts(breakdown, row_total):
    """Attribute one row's cost to provider buckets from its breakdown.

    Returns a dict {provider: usd}. Understands both the LOCAL-613 shape
    (gemini_grounding as a nested {usd,requests,queries}) and flat numeric fields
    (llm/tts/search from the older LOCAL-60 breakdown). Any row whose breakdown
    carries no recognised provider dollars is attributed to ``unattributed`` at
    its full row total, so the by-provider column always reconciles to the by-user
    total."""
    b = _as_dict(breakdown)
    out = {}

    def _num(v):
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            return 0.0

    # LOCAL-613 / LOCAL-609 fields
    out["openai"] = _num(b.get("openai")) + _num(b.get("llm"))  # llm == openai
    gg = b.get("gemini_grounding")
    if isinstance(gg, dict):
        out["gemini_grounding"] = _num(gg.get("usd"))
    else:
        out["gemini_grounding"] = _num(gg)
    out["gemini_tokens"] = _num(b.get("gemini_tokens"))
    out["serper"] = _num(b.get("serper")) + _num(b.get("search"))  # search == serper
    out["tts"] = _num(b.get("tts"))
    # preflight is a labelled SUBSET of gemini_grounding (a grounded Gemini call),
    # not an additive charge — it is surfaced for visibility but must NOT be
    # summed into the reconciliation, or a meter row would appear to cost more
    # than its row total.
    preflight = _num(b.get("preflight"))

    recognised = sum(out.values())  # preflight deliberately excluded here
    out = {k: v for k, v in out.items() if v > 0.0}
    if preflight > 0.0:
        out["preflight"] = preflight

    # Reconcile: if the breakdown's recognised dollars fall short of the row
    # total (rounding, or a provider line we don't name), park the remainder in
    # 'other'; if there was NO recognised breakdown at all, the whole row is
    # 'unattributed'.
    rt = _num(row_total)
    if recognised <= 0.0:
        if rt > 0.0:
            out["unattributed"] = rt
    else:
        remainder = round(rt - recognised, 6)
        if remainder > 0.000001:
            out["other"] = out.get("other", 0.0) + remainder
    return out


def fetch_rows(db_url, ts_from, ts_to):
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, operation_type, our_cost_usd, breakdown,
                       cache_hit, created_at, description
                FROM cost_ledger
                WHERE created_at >= %s AND created_at < %s
                ORDER BY created_at
                """,
                (ts_from, ts_to),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def build_report(rows, ts_from, ts_to):
    by_provider = {}
    by_user = {}
    live_total = 0.0
    test_total = 0.0
    row_total = 0.0

    for r in rows:
        uid = r.get("user_id") or "(none)"
        cost = float(r.get("our_cost_usd") or 0.0)
        row_total += cost

        is_test = str(uid).upper().startswith("TEST-")
        if is_test:
            test_total += cost
        else:
            live_total += cost

        u = by_user.setdefault(uid, {"usd": 0.0, "rows": 0, "is_test": is_test})
        u["usd"] += cost
        u["rows"] += 1

        for prov, amt in _provider_amounts(r.get("breakdown"), cost).items():
            by_provider[prov] = by_provider.get(prov, 0.0) + amt

    return {
        "window": {"from": ts_from.isoformat(), "to": ts_to.isoformat()},
        "row_count": len(rows),
        "grand_total_usd": round(row_total, 6),
        "live_total_usd": round(live_total, 6),
        "test_total_usd": round(test_total, 6),
        "by_provider": {k: round(by_provider.get(k, 0.0), 6)
                        for k in PROVIDER_ORDER if by_provider.get(k, 0.0) > 0.0},
        "by_user": {
            uid: {"usd": round(v["usd"], 6), "rows": v["rows"], "is_test": v["is_test"]}
            for uid, v in sorted(by_user.items(), key=lambda kv: -kv[1]["usd"])
        },
    }


def format_report(rep):
    w = rep["window"]
    lines = []
    lines.append("=" * 72)
    lines.append("COST LEDGER WINDOW REPORT  (LOCAL-613)")
    lines.append(f"window : {w['from']}  ->  {w['to']}")
    lines.append(f"rows   : {rep['row_count']}")
    lines.append(f"total  : ${rep['grand_total_usd']:.4f}   "
                 f"(live ${rep['live_total_usd']:.4f}  |  "
                 f"test ${rep['test_total_usd']:.4f})")
    lines.append("=" * 72)

    lines.append("\nBY PROVIDER")
    lines.append("-" * 72)
    if rep["by_provider"]:
        for prov in PROVIDER_ORDER:
            if prov in rep["by_provider"]:
                lines.append(f"  {prov:18} ${rep['by_provider'][prov]:.4f}")
    else:
        lines.append("  (no rows in window)")

    lines.append("\nBY USER  (LIVE users first, then TEST-* isolated runs)")
    lines.append("-" * 72)
    live = [(u, d) for u, d in rep["by_user"].items() if not d["is_test"]]
    test = [(u, d) for u, d in rep["by_user"].items() if d["is_test"]]
    if live:
        lines.append("  LIVE")
        for uid, d in live:
            lines.append(f"    {uid:28} ${d['usd']:.4f}   ({d['rows']} row(s))")
        lines.append(f"    {'— live subtotal —':28} ${rep['live_total_usd']:.4f}")
    if test:
        lines.append("  TEST (isolated runs)")
        for uid, d in test:
            lines.append(f"    {uid:28} ${d['usd']:.4f}   ({d['rows']} row(s))")
        lines.append(f"    {'— test subtotal —':28} ${rep['test_total_usd']:.4f}")
    if not live and not test:
        lines.append("  (no rows in window)")
    lines.append("=" * 72)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Total cost_ledger spend over a window, by provider and by user.")
    ap.add_argument("--from", dest="ts_from", required=True, type=parse_ts,
                    help="window start (inclusive). ISO 8601 or 'YYYY-MM-DD HH:MM'.")
    ap.add_argument("--to", dest="ts_to", required=True, type=parse_ts,
                    help="window end (exclusive). ISO 8601 or 'YYYY-MM-DD HH:MM'.")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text.")
    ap.add_argument("--db-url", default=None,
                    help="override the ledger connection URL (else DATABASE_URL / "
                         "DB_* env vars).")
    args = ap.parse_args(argv)

    if args.ts_to <= args.ts_from:
        ap.error("--to must be after --from")

    db_url = args.db_url or _get_db_url()
    try:
        rows = fetch_rows(db_url, args.ts_from, args.ts_to)
    except Exception as e:
        print(f"[cost_report_window] DB error: {e}", file=sys.stderr)
        return 2

    rep = build_report(rows, args.ts_from, args.ts_to)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(format_report(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
