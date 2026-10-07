#!/usr/bin/env python3
"""canary/report.py — CANARY.md / ALERTS.md writers and parsers for LOCAL-611.

The canary run appends a self-describing, machine-parseable block to
.continuous_dev/CANARY.md and, on any failure (or a budget stop), writes a
'*** CANARY FAIL ***' line to ALERTS.md. The run block carries a one-line
RUNSUMMARY marker that pass_rate_history / run_count parse to report the
pass-rate over the last 10 runs without re-reading the whole table.

Marker grammar (stable contract — tests assert it):
    <!-- CANARY-RUN idx=<n> ts=<iso> sha=<sha> pass=<p> total=<t> cost=<usd> budget_stopped=<bool> -->

Everything else in the block is human-facing Markdown (a per-tour table and
totals). The runner never edits these files by hand; it only appends.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
CONTINUOUS_DEV = os.path.join(PROJECT_ROOT, ".continuous_dev")
CANARY_MD = os.path.join(CONTINUOUS_DEV, "CANARY.md")
ALERTS_MD = os.path.join(PROJECT_ROOT, "ALERTS.md")

RUN_MARKER_RE = re.compile(
    r"<!--\s*CANARY-RUN\s+idx=(?P<idx>\d+)\s+ts=(?P<ts>\S+)\s+sha=(?P<sha>\S+)\s+"
    r"pass=(?P<pass>\d+)\s+total=(?P<total>\d+)\s+cost=(?P<cost>[\d.]+)\s+"
    r"budget_stopped=(?P<bs>\w+)\s*-->"
)


# --------------------------------------------------------------------------- #
# Git
# --------------------------------------------------------------------------- #
def git_sha(short: bool = True) -> str:
    try:
        args = ["git", "rev-parse", "--short" if short else "HEAD", "HEAD"]
        if not short:
            args = ["git", "rev-parse", "HEAD"]
        out = subprocess.check_output(args, cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------- #
# Parsing (history)
# --------------------------------------------------------------------------- #
def parse_runs(path: str = CANARY_MD) -> List[dict]:
    """Return a list of {idx, ts, sha, pass, total, cost, budget_stopped} dicts,
    one per recorded run, in file order."""
    if not os.path.exists(path):
        return []
    runs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = RUN_MARKER_RE.search(line)
            if m:
                runs.append({
                    "idx": int(m.group("idx")),
                    "ts": m.group("ts"),
                    "sha": m.group("sha"),
                    "pass": int(m.group("pass")),
                    "total": int(m.group("total")),
                    "cost": float(m.group("cost")),
                    "budget_stopped": m.group("bs").lower() == "true",
                })
    return runs


def run_count(path: str = CANARY_MD) -> int:
    """Number of runs already recorded (used as the next run's 0-based index)."""
    return len(parse_runs(path))


def pass_rate_history(path: str = CANARY_MD, last: int = 10) -> dict:
    """Pass-rate over the last `last` runs.

    Returns {runs, tours_passed, tours_total, rate, per_run: [...]} where
    per_run is a list of "p/t" strings, newest last.
    """
    runs = parse_runs(path)[-last:]
    tp = sum(r["pass"] for r in runs)
    tt = sum(r["total"] for r in runs)
    return {
        "runs": len(runs),
        "tours_passed": tp,
        "tours_total": tt,
        "rate": round(tp / tt, 4) if tt else 0.0,
        "per_run": [f"{r['pass']}/{r['total']}" for r in runs],
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _fmt_cost(c: dict) -> str:
    total = c.get("total", 0.0)
    bd = c.get("breakdown") or {}
    if bd:
        parts = ", ".join(f"{k} ${float(v):.4f}" for k, v in sorted(bd.items()))
        return f"${total:.4f} ({parts})"
    return f"${total:.4f}"


def render_run_block(summary: dict) -> str:
    """Render one run's Markdown block (header, marker, per-tour table, totals)."""
    results = summary.get("results", [])
    n_pass = sum(1 for r in results if r.get("success"))
    n_total = len(results)
    idx = summary.get("run_index", 0)
    ts = summary.get("timestamp", datetime.utcnow().isoformat())
    sha = summary.get("code_sha", "unknown")
    cost = summary.get("total_cost", 0.0)
    bs = summary.get("budget_stopped", False)

    lines = []
    lines.append("")
    lines.append(f"## Canary run #{idx + 1} — {ts}")
    lines.append("")
    lines.append(
        f"<!-- CANARY-RUN idx={idx} ts={ts} sha={sha} pass={n_pass} "
        f"total={n_total} cost={cost:.6f} budget_stopped={str(bs).lower()} -->"
    )
    lines.append("")
    lines.append(f"- Code SHA: `{sha}`")
    lines.append(f"- Result: **{n_pass}/{n_total} passed**"
                 + ("  — **BUDGET STOP**" if bs else ""))
    lines.append(f"- Cost: **${cost:.4f}** (cap ${summary.get('cap_usd', 3.0):.2f})")
    lines.append(f"- audio_tours rows: {summary.get('count_before', '?')} → "
                 f"{summary.get('count_after', '?')} "
                 f"(+{(summary.get('count_after') or 0) - (summary.get('count_before') or 0)} is_test)")
    pm = summary.get("pool_meta") or {}
    if pm:
        lines.append(f"- Venue pool: {pm.get('rows', '?')} rows / "
                     f"{pm.get('countries', '?')} countries (built {pm.get('built_at', '?')})")
    lines.append("")
    lines.append("| Tour | Group | Loc | Req | Deliv | OK | Coords | is_test | URL | ChkSite | Wall(s) | Cost | Error |")
    lines.append("|------|-------|-----|-----|-------|----|--------|---------|-----|---------|---------|------|-------|")
    for r in results:
        ok = "✅" if r.get("success") else "❌"
        coords = "y" if r.get("coordinates_present") else ("n" if r.get("coordinates_present") is not None else "?")
        istest = "y" if r.get("is_test") else ("n" if r.get("is_test") is not None else "?")
        url = "y" if r.get("url_in_audio") else ("n" if r.get("url_in_audio") is not None else "?")
        err = (r.get("error_code") or "")
        if r.get("error_message") and not r.get("success"):
            err = f"{err}: {r['error_message']}"
        err = err.replace("|", "/").replace("\n", " ")[:80]
        loc = (r.get("location") or "").replace("|", "/")[:40]
        lines.append(
            f"| {r.get('name','')} | {r.get('group','')} | {loc} | "
            f"{r.get('requested_stops','')} | {r.get('delivered_stops','')} | {ok} | "
            f"{coords} | {istest} | {url} | {r.get('check_site_count','')} | "
            f"{r.get('wall_s','')} | {_fmt_cost(r.get('cost', {}))} | {err} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Writers (append-only)
# --------------------------------------------------------------------------- #
def _ensure_header(path: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# CANARY — live canary gate history (LOCAL-611)\n\n")
        fh.write("Each run tries the 5 known venues PLUS 3 never-seen venues from "
                 "the Wikidata pool. Appended automatically by `canary/run_canary.py`; "
                 "do not edit by hand.\n")


def append_canary_report(summary: dict, path: str = CANARY_MD) -> str:
    """Append one run block to CANARY.md. Returns the rendered block."""
    _ensure_header(path)
    block = render_run_block(summary)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(block)
    return block


def write_alert(summary: dict, path: str = ALERTS_MD) -> str:
    """Append a '*** CANARY FAIL ***' line (+ per-failure detail) to ALERTS.md."""
    results = summary.get("results", [])
    fails = [r for r in results if not r.get("success")]
    idx = summary.get("run_index", 0)
    ts = summary.get("timestamp", datetime.utcnow().isoformat())
    sha = summary.get("code_sha", "unknown")
    header_needed = not os.path.exists(path)
    lines = []
    if header_needed:
        lines.append("# ALERTS\n")
    reason = []
    if fails:
        reason.append(f"{len(fails)} tour failure(s)")
    if summary.get("budget_stopped"):
        reason.append("budget stop")
    lines.append(
        f"\n*** CANARY FAIL *** run #{idx + 1} @ {ts} sha={sha}: "
        f"{', '.join(reason) or 'failure'}"
    )
    for r in fails:
        lines.append(
            f"  - {r.get('name','')} [{r.get('group','')}] "
            f"{(r.get('location') or '')[:50]}: "
            f"{r.get('error_code','')} {('— ' + r['error_message']) if r.get('error_message') else ''}"
        )
    text = "\n".join(lines) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)
    return text
