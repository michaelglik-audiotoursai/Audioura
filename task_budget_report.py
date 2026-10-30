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

Exit status
===========
    0  within budget (or budget unknown)
    2  recorded total is over the stored budget   (so a wrapper/CI can notice)
    1  no ledger exists for the id / bad usage
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import task_budget  # noqa: E402


def _fmt_usd(v):
    try:
        return "$%.4f" % float(v or 0.0)
    except (TypeError, ValueError):
        return "$?"


def build_report_text(task_id):
    """Return (text, exit_code) for ``task_id`` without touching stdout, so this
    is unit-testable."""
    ledger = task_budget.load_ledger(task_id)
    runs = ledger.get("runs") or []
    path = task_budget.ledger_path(task_id)

    if not runs and not os.path.exists(path):
        return ("No ledger for task %s (%s). No runs recorded yet."
                % (task_id, path), 1)

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
