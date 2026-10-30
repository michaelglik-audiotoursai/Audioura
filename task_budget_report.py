#!/usr/bin/env python3
"""task_budget_report.py — print a task's recorded paid-API runs and total (LOCAL-817).

Usage
=====
    python3 task_budget_report.py LOCAL-816
    python3 task_budget_report.py                 # uses $TASK_BUDGET_ID

Reads the append-only ledger at ``~/.audioura_task_budgets/<id>.json`` (dir
overridable with ``AUDIOURA_TASK_BUDGET_DIR``) that LiveRunMeter writes one row to
per run, and prints each run's timestamp and dollars, the running total, the
configured budget, and the remaining headroom. Read-only: it never writes or
enforces anything, so it is safe to run any time to answer "how much has this task
spent so far, and is it over?".

[LOCAL-827] METER-LOG FALLBACK. When no ledger exists for the id (the common case
for a run whose container never bind-mounted the ledger dir, which is the very bug
LOCAL-827 fixes — LOCAL-823/824 reported "No ledger … No runs recorded yet"), the
report falls back to summing the CANONICAL METER LOG by service: every billed row
whose ``service == <id>`` in ``~/Audioura/meterlogs/*.jsonl``. That is the same
sum the LOCAL-827 raw-door cap enforces, so the report still answers "how much has
this task spent?" from the meter's own records even when LiveRunMeter never wrote
a ledger row. The meter-log dir is overridable with ``AUDIOURA_METERLOG_DIR`` (and
individual globs with ``--log``) so a test can point it at a tmpdir.

Exit status
===========
    0  within budget (or budget unknown)
    2  recorded total is over the stored budget   (so a wrapper/CI can notice)
    1  no ledger exists for the id / bad usage
"""
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import task_budget  # noqa: E402


# [LOCAL-827] The canonical meter-log dir the fallback sums. Matches
# meter_report.py's default (~/Audioura/meterlogs/*.jsonl); overridable with
# AUDIOURA_METERLOG_DIR so a test can point it at a tmpdir.
def _meterlog_glob():
    d = os.environ.get("AUDIOURA_METERLOG_DIR")
    if not d:
        d = os.path.join(os.path.expanduser("~"), "Audioura", "meterlogs")
    return os.path.join(d, "*.jsonl")


def sum_meter_log_for_service(task_id, log_glob=None):
    """[LOCAL-827] Return (total_usd, n_rows) summing billed (status 200) ``usd``
    for rows whose ``service == task_id`` across the canonical meter logs. A
    missing dir / no logs read as (0.0, 0). Read-only and fail-open: a malformed
    line or unreadable file is skipped, never raised."""
    total = 0.0
    n = 0
    spec = log_glob or _meterlog_glob()
    try:
        paths = sorted(glob.glob(os.path.expanduser(spec)))
    except Exception:
        paths = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("service") or "") != str(task_id):
                        continue
                    status = row.get("status")
                    if status is not None and status != 200:
                        continue
                    try:
                        total += float(row.get("usd") or 0.0)
                        n += 1
                    except (TypeError, ValueError):
                        continue
        except Exception:
            continue
    return total, n


def _fmt_usd(v):
    try:
        return "$%.4f" % float(v or 0.0)
    except (TypeError, ValueError):
        return "$?"


def _meter_log_fallback_text(task_id, log_glob=None):
    """[LOCAL-827] Build the report for a task that has NO ledger, from the meter
    log alone. Returns (text, exit_code). When the meter log also has no rows for
    the id, returns the original "no ledger" message (exit 1); otherwise it prints
    the metered total, the env budget (if set) and remaining headroom, and exits 2
    when over budget — so a wrapper/CI notices an over-budget task even when
    LiveRunMeter never wrote a ledger."""
    total, n = sum_meter_log_for_service(task_id, log_glob=log_glob)
    path = task_budget.ledger_path(task_id)
    if n == 0:
        return ("No ledger for task %s (%s). No runs recorded yet. "
                "No metered rows for service=%s either."
                % (task_id, path, task_id), 1)

    budget = task_budget.budget_usd_from_env()
    lines = []
    lines.append("Task budget report: %s" % task_id)
    lines.append("Ledger: %s  (none — summing the meter log instead, LOCAL-827)"
                 % path)
    lines.append("Source: meter log %s" % (log_glob or _meterlog_glob()))
    lines.append("")
    lines.append("  metered rows (service=%s): %d" % (task_id, n))
    lines.append("  %-22s %s" % ("METERED TOTAL", _fmt_usd(total)))
    exit_code = 0
    lines.append("")
    if budget is None:
        lines.append("Budget:    (unknown — TASK_BUDGET_USD not set and no ledger)")
        lines.append("Remaining: (unknown)")
    else:
        remaining = float(budget) - total
        lines.append("Budget:    %s" % _fmt_usd(budget))
        lines.append("Remaining: %s" % _fmt_usd(remaining))
        if total > float(budget) + 1e-9:
            lines.append("")
            lines.append("*** OVER BUDGET by %s ***" % _fmt_usd(total - float(budget)))
            exit_code = 2
    return ("\n".join(lines), exit_code)


def build_report_text(task_id):
    """Return (text, exit_code) for ``task_id`` without touching stdout, so this
    is unit-testable."""
    ledger = task_budget.load_ledger(task_id)
    runs = ledger.get("runs") or []
    path = task_budget.ledger_path(task_id)

    if not runs and not os.path.exists(path):
        # [LOCAL-827] No ledger file at all — fall back to the meter log by
        # service. This is the whole point of 827: a run whose container never
        # mounted the ledger dir leaves no ledger, but its metered rows are on the
        # host, so the task's spend is still answerable.
        return _meter_log_fallback_text(task_id)

    # Budget: prefer the live env (what the next run would use); else the value
    # stored in the ledger from the last write.
    env_budget = task_budget.budget_usd_from_env()
    budget = env_budget if env_budget is not None else ledger.get("budget_usd")

    lines = []
    lines.append("Task budget report: %s" % task_id)
    lines.append("Ledger: %s" % path)
    lines.append("")
    lines.append("  %-22s %12s  %s" % ("when (UTC)", "usd", "note"))
    lines.append("  " + "-" * 58)
    total = 0.0
    for run in runs:
        try:
            usd = float(run.get("usd") or 0.0)
        except (TypeError, ValueError):
            usd = 0.0
        total += usd
        flag = "  [CAPPED]" if run.get("capped") else ""
        lines.append("  %-22s %12s  %s%s" % (
            run.get("ts", "?"), _fmt_usd(usd), run.get("note", ""), flag))
    lines.append("  " + "-" * 58)
    lines.append("  %-22s %12s" % ("TOTAL (%d runs)" % len(runs), _fmt_usd(total)))

    exit_code = 0
    lines.append("")
    if budget is None:
        lines.append("Budget:    (unknown — TASK_BUDGET_USD not set and none stored)")
        lines.append("Remaining: (unknown)")
    else:
        remaining = float(budget) - total
        lines.append("Budget:    %s" % _fmt_usd(budget))
        lines.append("Remaining: %s" % _fmt_usd(remaining))
        if total > float(budget) + 1e-9:
            lines.append("")
            lines.append("*** OVER BUDGET by %s ***" % _fmt_usd(total - float(budget)))
            exit_code = 2
    return ("\n".join(lines), exit_code)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    task_id = argv[0] if argv else task_budget.task_id_from_env()
    if not task_id:
        sys.stderr.write(
            "usage: task_budget_report.py <task-id>   "
            "(or set TASK_BUDGET_ID)\n")
        return 1
    text, code = build_report_text(task_id)
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
