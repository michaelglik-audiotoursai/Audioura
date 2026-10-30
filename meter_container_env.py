#!/usr/bin/env python3
"""meter_container_env.py — the ONE standard way to wire the paid-API meter into
an isolated task container so its spend lands where LEAD sums it (LOCAL-819).

THE GAP THIS CLOSES
-------------------
Isolated task runs (``docker run --rm --name localNNN-…`` / the run_local*_live.sh
wrappers) each wrote their meter log to a DIFFERENT place, or not to the shared
dir at all: some mounted ``~/Audioura/meterlogs`` under a per-task filename
(paid_api_calls_localNNN.jsonl), most set no METER_SERVICE, and only one task
(local814) tagged its rows. So a task's OpenAI/Gemini/Serper spend was invisible
to a single ``meter_report.py`` sweep — the ~$29 Mac-key gap in the ticket.

THE CONTRACT (adopt this and a task's spend is counted)
-------------------------------------------------------
Every isolated container MUST:
  * bind-mount the host meterlog dir  ~/Audioura/meterlogs  ->  /meterlogs
  * write to the CANONICAL log         PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
    (one file every sweep reads; the meter's _lock makes concurrent appends safe)
  * tag its rows with the task id      METER_SERVICE=<task id>   (e.g. LOCAL-819)
  * install the meter                  PYTHONPATH=/opt/meter (sitecustomize) OR
                                        `import _meter.meter_bootstrap`
  * optionally tag the key             METER_KEY_SUFFIX=<last 4 of the key>

Because the meter now ALSO defaults `service` to TASK_BUDGET_ID when METER_SERVICE
is unset (see paid_api_meter._default_service), any container that already sets
TASK_BUDGET_ID for the LOCAL-817 budget is tagged correctly for free. This helper
is the explicit, self-documenting path for runners that want to be certain.

USAGE (building a `docker run` argv in a Python runner)
-------------------------------------------------------
    import meter_container_env as mce
    args = ["docker", "run", "--rm", "--name", f"{task}-tg"]
    args += mce.docker_meter_args(task_id="LOCAL-819", meter_dir=repo_meter_dir,
                                  key_suffix="k9sA")
    args += ["-v", f"{code_dir}:/app", "-w", "/app", image, "python", "-u", runner]

USAGE (in-process, a host harness or container entrypoint)
----------------------------------------------------------
    import meter_container_env as mce
    mce.apply_meter_env(task_id="LOCAL-819")   # sets env + installs the meter
"""
import os
import sys

HOST_METER_DIR = os.path.join(os.path.expanduser("~"), "Audioura", "meterlogs")
CONTAINER_METER_DIR = "/meterlogs"
CANONICAL_LOG = CONTAINER_METER_DIR + "/paid_api_calls.jsonl"

# [LOCAL-827] The WHOLE-TASK budget ledger dir (LOCAL-817). task_budget.py and
# LiveRunMeter write ~/.audioura_task_budgets/<id>.json; the raw meter door and
# task_budget_report.py read it. Before 827 this dir was NEVER mounted into the
# isolated --rm containers, so every run's LiveRunMeter wrote its ledger INSIDE
# the container, which --rm destroyed — so the whole-task cap (LOCAL-817) started
# from $0 every run and never accumulated across runs (LOCAL-821B spent $0.81 vs
# $0.40; LOCAL-823/824 reported "No ledger … No runs recorded yet"). Mounting the
# host dir at the SAME path the container's _task_budget_dir() default resolves to
# makes every isolated run of a task share ONE ledger.
HOST_TASK_BUDGET_DIR = os.path.join(os.path.expanduser("~"), ".audioura_task_budgets")
CONTAINER_TASK_BUDGET_DIR = "/task_budgets"


def docker_meter_args(task_id, meter_dir, host_meter_dir=HOST_METER_DIR,
                      key_suffix=None, host_task_budget_dir=HOST_TASK_BUDGET_DIR,
                      task_budget_usd=None, env=None):
    """Return the ``docker run`` argv fragment that bind-mounts the shared
    meterlog dir, installs the meter (PYTHONPATH=/opt/meter), writes the canonical
    log and tags every row ``service=<task_id>`` — AND [LOCAL-827] bind-mounts the
    shared whole-task budget ledger dir so every isolated run of a task shares ONE
    ledger, and arms the whole-task cap (TASK_BUDGET_ID / TASK_BUDGET_USD).

    meter_dir            — the repo's ``_meter`` directory on the host (mounted
                           read-only at /opt/meter so sitecustomize installs the
                           meter).
    host_meter_dir       — host dir to bind at /meterlogs (default
                           ~/Audioura/meterlogs); created if missing so the mount
                           never fails.
    key_suffix           — optional last-few chars of the paid-API key (NOT the key).
    host_task_budget_dir — [LOCAL-827] host dir holding the per-task JSON ledgers
                           (default ~/.audioura_task_budgets); created if missing
                           and bind-mounted at /task_budgets, with
                           AUDIOURA_TASK_BUDGET_DIR pointing the container there, so
                           LiveRunMeter's ledger and the raw door's meter-log cap
                           both persist to the host across --rm.
    task_budget_usd      — [LOCAL-827] the whole-task budget in dollars. When None,
                           falls back to the caller's TASK_BUDGET_USD env. When a
                           value is resolved, TASK_BUDGET_ID is set to ``task_id``
                           and TASK_BUDGET_USD to the budget, arming the LOCAL-817
                           whole-task cap and the LOCAL-827 meter-log cap inside the
                           container.
    env                  — env mapping the budget vars are read from (defaults to
                           os.environ); lets a caller/test pass an explicit env.
    """
    try:
        os.makedirs(host_meter_dir, exist_ok=True)
    except Exception:
        pass
    # [LOCAL-827] Create the shared ledger dir so the bind-mount never fails
    # (mirrors the meterlog dir handling above).
    try:
        os.makedirs(host_task_budget_dir, exist_ok=True)
    except Exception:
        pass
    args = [
        "-e", "PYTHONPATH=/opt/meter",
        "-e", "PAID_API_LOG=" + CANONICAL_LOG,
        "-e", "METER_SERVICE=" + str(task_id),
        # [LOCAL-827] Point the container's task-budget code at the mounted dir.
        "-e", "AUDIOURA_TASK_BUDGET_DIR=" + CONTAINER_TASK_BUDGET_DIR,
        "-v", "%s:/opt/meter:ro" % meter_dir,
        "-v", "%s:%s" % (host_meter_dir, CONTAINER_METER_DIR),
        # [LOCAL-827] The shared whole-task budget ledger dir, so every isolated
        # run of a task reads/writes the SAME ledger instead of a throwaway one
        # inside the --rm container.
        "-v", "%s:%s" % (host_task_budget_dir, CONTAINER_TASK_BUDGET_DIR),
    ]
    # [LOCAL-827] Arm the whole-task cap: TASK_BUDGET_ID is the task id (so the
    # meter-log cap keys on service==task_id); TASK_BUDGET_USD is the budget,
    # resolved from the arg or the caller's env. Setting TASK_BUDGET_ID also keeps
    # the LOCAL-822 mount guard armed, exactly as the .sh wrappers do by hand.
    _env = os.environ if env is None else env
    budget = task_budget_usd
    if budget is None:
        try:
            raw = _env.get("TASK_BUDGET_USD")
            if raw is not None and str(raw).strip() != "":
                budget = str(raw).strip()
        except Exception:
            budget = None
    else:
        budget = str(budget)
    if budget is not None:
        args += ["-e", "TASK_BUDGET_ID=" + str(task_id),
                 "-e", "TASK_BUDGET_USD=" + str(budget)]
    if key_suffix:
        args += ["-e", "METER_KEY_SUFFIX=" + str(key_suffix)[-8:]]
    return args


def meter_env(task_id, key_suffix=None, log=CANONICAL_LOG):
    """The env dict a container/entrypoint should carry so its rows are metered to
    the canonical shared log and tagged with the task id. Does not touch
    os.environ; merge it yourself or use apply_meter_env()."""
    env = {
        "PAID_API_LOG": log,
        "METER_SERVICE": str(task_id),
    }
    if key_suffix:
        env["METER_KEY_SUFFIX"] = str(key_suffix)[-8:]
    return env


def apply_meter_env(task_id, key_suffix=None, log=CANONICAL_LOG, install=True):
    """Set the meter env vars in THIS process (only where not already set) and,
    when install=True, install the network meter via meter_bootstrap. Call this as
    the first thing a container entrypoint / host harness does. Never raises —
    metering must not break a run. Returns True when the meter is active."""
    try:
        for k, v in meter_env(task_id, key_suffix=key_suffix, log=log).items():
            os.environ.setdefault(k, v)
    except Exception:
        pass
    if not install:
        return False
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        meter_dir = os.path.join(here, "_meter")
        if meter_dir not in sys.path:
            sys.path.insert(0, meter_dir)
        import meter_bootstrap  # noqa: F401  (installs on import)
        import paid_api_meter
        return bool(getattr(paid_api_meter, "_INSTALLED", False))
    except Exception as e:
        try:
            sys.stderr.write("[meter_container_env] meter not installed: %s\n"
                             % (str(e)[:200],))
        except Exception:
            pass
        return False
