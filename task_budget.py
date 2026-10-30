#!/usr/bin/env python3
"""task_budget.py — WHOLE-TASK paid-API budget ledger + cap (LOCAL-817).

Why this exists
===============
A task file says "Paid-API cap $X TOTAL across all runs", but the only mechanism
that enforced a cap — ``tests/live_run_meter.LiveRunMeter`` — enforced it PER RUN
(``TEST_GEMINI_MAX_USD``). During debugging a task is re-run many times, and each
run was allowed up to the full per-run cap again, so the TOTAL quietly ran past
the number in the task file every time:

    LOCAL-810  $2.88 spent vs $1.00 cap     LOCAL-816  $1.47 vs $0.60
    LOCAL-814B $0.68  vs $0.60 cap          LOCAL-802  $1.29 vs $1.20

Instructions alone did not hold (Kiro overspent 3x on 2026-10-29). This module
makes the whole-task cap mechanical: every run records its spend into a small
append-only JSON ledger, and a run is REFUSED (before it starts, and again mid-run
at the grounding counter) the moment ``spent_so_far + this_run > budget``.

The ledger
==========
One file per task at ``~/.audioura_task_budgets/<id>.json``:

    {"task_id": "LOCAL-816", "budget_usd": 0.60,
     "runs": [{"ts": "2026-10-29T20:00:00Z", "usd": 0.31, "note": "run 1"},
              {"ts": "2026-10-29T20:40:00Z", "usd": 0.29, "note": "run 2"}]}

``runs`` is append-only; ``spent_so_far`` is their sum. The budget is taken from
the env (``TASK_BUDGET_USD``) on each write so raising the number in the task file
takes effect immediately; the stored ``budget_usd`` is the last value seen (for
the report).

Env contract
============
A live run MUST export both (LEAD puts them in the task file):

    TASK_BUDGET_ID   e.g. "LOCAL-816"   — which task's ledger to use
    TASK_BUDGET_USD  e.g. "0.60"        — the whole-task cap in dollars

When ``TASK_BUDGET_ID`` is unset the whole-task cap is OFF and the old per-run
behaviour (``TEST_GEMINI_MAX_USD`` only) is unchanged — this module's public
functions become no-ops. This keeps every existing harness working untouched.

Fail philosophy
===============
The whole-task cap is a HARD STOP (it raises ``BudgetExceeded``) — that is the
point; an over-budget run must not proceed. But a LEDGER I/O problem must never
by itself block a run that is within budget: a corrupt/unreadable ledger is
treated as "no runs recorded yet" (fail-open on read) so a disk glitch cannot
wedge a task. Writes are best-effort and never raise into the caller.
"""
import json
import os
import tempfile
import threading
import time

__all__ = [
    "BudgetExceeded",
    "budget_dir",
    "ledger_path",
    "task_id_from_env",
    "budget_usd_from_env",
    "load_ledger",
    "spent_so_far",
    "record_run",
    "check_task_budget",
    "would_exceed",
]

# Default reserve ($) assumed for a run that has not spent anything measurable
# yet, used by the refuse-to-start check so two runs that would each spend a
# little still cannot be started once the remaining headroom is tiny. Small on
# purpose: the real stop is the mid-run grounding guard; this only blocks a run
# that starts with essentially no headroom left.
DEFAULT_RESERVE_USD = 0.01

_BUDGET_DIRNAME = ".audioura_task_budgets"
_lock = threading.Lock()


class BudgetExceeded(Exception):
    """Raised when starting or continuing a run would push the task's TOTAL
    paid-API spend past ``TASK_BUDGET_USD``. The run stops cleanly with an honest
    error (the tour clean-fails; the submission must report it) rather than
    silently overspending as happened on 2026-10-29."""


# ── env ───────────────────────────────────────────────────────────────────────
def task_id_from_env():
    """The task whose ledger is active, or None when the whole-task cap is off."""
    raw = os.environ.get("TASK_BUDGET_ID")
    if raw is None:
        return None
    raw = str(raw).strip()
    return raw or None


def budget_usd_from_env():
    """The whole-task cap in USD from ``TASK_BUDGET_USD``, or None when unset /
    blank / unparseable / non-positive (cap off). Fail-safe: a malformed value
    disables the whole-task cap rather than inventing one."""
    raw = os.environ.get("TASK_BUDGET_USD")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    # A budget of exactly $0 is a MEANINGFUL cap (allow zero paid spend), so it is
    # kept; only a negative value is treated as "off".
    return val if val >= 0 else None


# ── ledger location ─────────────────────────────────────────────────────────--
def budget_dir():
    """Directory holding the per-task ledgers. Overridable with
    ``AUDIOURA_TASK_BUDGET_DIR`` (tests point it at a tmpdir)."""
    override = os.environ.get("AUDIOURA_TASK_BUDGET_DIR")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), _BUDGET_DIRNAME)


def _safe_id(task_id):
    """Filesystem-safe form of a task id (keeps letters, digits, dash, underscore,
    dot). Prevents a crafted id from escaping the budget dir."""
    s = str(task_id).strip()
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in s) or "task"


def ledger_path(task_id):
    """Absolute path of the ledger file for ``task_id``."""
    return os.path.join(budget_dir(), _safe_id(task_id) + ".json")


# ── ledger I/O ────────────────────────────────────────────────────────────────
def load_ledger(task_id):
    """Return the ledger dict for ``task_id``. A missing/corrupt/unreadable file
    yields a fresh empty ledger (fail-open on read: a disk glitch must not wedge a
    task that is within budget)."""
    path = ledger_path(task_id)
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("ledger is not a JSON object")
        data.setdefault("task_id", str(task_id))
        runs = data.get("runs")
        if not isinstance(runs, list):
            data["runs"] = []
        return data
    except FileNotFoundError:
        return {"task_id": str(task_id), "budget_usd": None, "runs": []}
    except Exception:
        # Corrupt or unreadable — treat as no runs recorded yet. The mid-run
        # grounding guard still protects this run; only the historical total is
        # lost, which fails toward allowing work rather than wedging the task.
        return {"task_id": str(task_id), "budget_usd": None, "runs": []}


def spent_so_far(task_id):
    """Sum of every recorded run's dollars for ``task_id`` (0.0 when none)."""
    total = 0.0
    for run in load_ledger(task_id).get("runs", []):
        try:
            total += float(run.get("usd") or 0.0)
        except (TypeError, ValueError):
            continue
    return round(total, 6)


def _atomic_write(path, data):
    """Write ``data`` (a dict) to ``path`` atomically via a temp file + rename, so
    a concurrent reader never sees a half-written ledger."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tb-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def record_run(task_id, usd, note=None, capped=False):
    """Append one run's spend to the task ledger and return the updated dict.

    Append-only: existing runs are never rewritten. ``budget_usd`` is refreshed
    from the env on each write so raising the task-file number takes effect at
    once. Best-effort: a write failure is swallowed (metering must not break a
    run — the whole bug was spend that left no trace, but a crash here would make
    it worse) and the in-memory ledger is still returned.
    """
    with _lock:
        ledger = load_ledger(task_id)
        try:
            usd_f = max(0.0, float(usd or 0.0))
        except (TypeError, ValueError):
            usd_f = 0.0
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "usd": round(usd_f, 6),
        }
        if note:
            entry["note"] = str(note)
        if capped:
            entry["capped"] = True
        ledger.setdefault("runs", []).append(entry)
        env_budget = budget_usd_from_env()
        if env_budget is not None:
            ledger["budget_usd"] = round(env_budget, 6)
        try:
            _atomic_write(ledger_path(task_id), ledger)
        except Exception:
            pass  # best-effort; never break the run on a ledger write failure
        return ledger


# ── the cap ─────────────────────────────────────────────────────────────────--
def would_exceed(task_id, budget_usd, pending_usd):
    """True when ``spent_so_far + pending_usd`` strictly exceeds ``budget_usd``.

    The comparison is strict (>) so a run that lands EXACTLY on the budget is
    allowed; only crossing past it is refused. A tiny epsilon absorbs float noise
    so e.g. three $0.20 runs against a $0.60 budget do not trip on rounding."""
    if budget_usd is None:
        return False
    spent = spent_so_far(task_id)
    return (spent + max(0.0, float(pending_usd or 0.0))) > (float(budget_usd) + 1e-9)


def check_task_budget(pending_usd=0.0, task_id=None, budget_usd=None):
    """Enforce the WHOLE-TASK cap. Raise ``BudgetExceeded`` when
    ``spent_so_far(task) + pending_usd`` would exceed the task budget; return the
    remaining headroom (float) otherwise.

    No-op (returns None) when the whole-task cap is OFF — i.e. ``TASK_BUDGET_ID``
    is unset or ``TASK_BUDGET_USD`` is unset/non-positive. This is the single
    function both the raw meter door and ``LiveRunMeter`` call; keeping the env
    read here means "cap off" behaves identically everywhere.

    pending_usd:
        The dollars this call/run is about to spend (or has spent so far in the
        current run), ON TOP of what the ledger already holds.
    task_id / budget_usd:
        Override the env values (used by callers that already resolved them, and
        by tests). When omitted they come from the env.
    """
    tid = task_id if task_id is not None else task_id_from_env()
    if not tid:
        return None  # whole-task cap off
    budget = budget_usd if budget_usd is not None else budget_usd_from_env()
    if budget is None:
        return None  # no budget configured -> cap off
    spent = spent_so_far(tid)
    pending = max(0.0, float(pending_usd or 0.0))
    if (spent + pending) > (float(budget) + 1e-9):
        raise BudgetExceeded(
            "[LOCAL-817] task %s: whole-task paid-API spend "
            "$%.4f already + $%.4f this run = $%.4f > budget $%.4f "
            "(TASK_BUDGET_USD). Refusing — set a higher TASK_BUDGET_USD or start a "
            "fresh task id if this is intended." % (
                tid, spent, pending, spent + pending, float(budget)))
    return round(float(budget) - spent - pending, 6)


if __name__ == "__main__":  # tiny self-check, no network, no DB
    import sys
    tid = "SELFTEST-LOCAL-817"
    os.environ["AUDIOURA_TASK_BUDGET_DIR"] = tempfile.mkdtemp(prefix="tb-selftest-")
    os.environ["TASK_BUDGET_ID"] = tid
    os.environ["TASK_BUDGET_USD"] = "0.60"
    try:
        record_run(tid, 0.31, note="run 1")
        record_run(tid, 0.25, note="run 2")
        print("spent_so_far:", spent_so_far(tid))
        try:
            check_task_budget(0.10)  # 0.56 + 0.10 = 0.66 > 0.60
            print("ERROR: expected BudgetExceeded")
            sys.exit(1)
        except BudgetExceeded as e:
            print("refused as expected:", str(e)[:80], "...")
        print("OK")
    finally:
        import shutil
        shutil.rmtree(os.environ["AUDIOURA_TASK_BUDGET_DIR"], ignore_errors=True)
