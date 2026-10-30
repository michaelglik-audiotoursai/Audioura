#!/usr/bin/env python3
"""run_local827_container.py — LOCAL-827 live acceptance, container side.

Proves the WHOLE-TASK budget now accumulates ACROSS isolated --rm containers.

This is the tiny, DB-free, single-purpose harness the ticket's "Live — BUDGET
ENFORCED" step runs INSIDE each disposable container (never an audioura-* one,
never the live DB). It makes a handful of the smallest possible paid OpenAI calls
(model gpt-4o, max_tokens=1, a one-token prompt) straight through ``requests`` —
which the baked-in meter (PYTHONPATH=/opt/meter) patches, so every call is:

  * recorded to the CANONICAL meter log (PAID_API_LOG=/meterlogs/paid_api_calls.jsonl,
    bind-mounted to the host so it survives --rm), tagged service=LOCAL-827, and
  * checked against the LOCAL-827 meter-log cap BEFORE it is sent: once the summed
    ``usd`` of this task's rows across ALL its containers reaches TASK_BUDGET_USD,
    the meter raises TaskBudgetExceeded and the call never reaches the network.

Run it TWICE, in two separate ``docker run --rm`` containers under the SAME
TASK_BUDGET_ID=LOCAL-827 / TASK_BUDGET_USD=0.0002 (see run_local827_live.sh). The
first container spends up toward the cap; the second container sees the first's
spend in the shared log and is refused almost immediately — the exact cross-run
accumulation that was broken before 827 (LOCAL-821B spent $0.81 vs $0.40).

Exit status
-----------
    0  ran to completion (made some calls, and/or was correctly refused by the cap)
    3  no OPENAI_API_KEY in the container env (cannot prove a live call)
Prints a REFUSED line (with the TaskBudgetExceeded message) the instant the cap
fires, so the wrapper and the submission can show the stop.
"""
import os
import sys
import time

# The meter is installed via PYTHONPATH=/opt/meter (sitecustomize). Import it so
# we can name its TaskBudgetExceeded exactly; fall back to a broad except if the
# import path differs, so the proof still records the refusal.
try:
    sys.path.insert(0, "/opt/meter")
    import paid_api_meter  # noqa: E402
    TaskBudgetExceeded = paid_api_meter.TaskBudgetExceeded
except Exception:  # pragma: no cover - meter always present in the image
    paid_api_meter = None

    class TaskBudgetExceeded(Exception):
        pass

import requests  # noqa: E402

TASK = os.environ.get("TASK_BUDGET_ID", "LOCAL-827")
BUDGET = os.environ.get("TASK_BUDGET_USD", "?")
LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
MAX_CALLS = int(os.environ.get("LOCAL827_MAX_CALLS", "6"))

KEY = os.environ.get("OPENAI_API_KEY", "").strip()


def _tiny_openai_call(i):
    """One tiny paid OpenAI call: a short prompt, max_tokens=5 (the ticket's
    ``max_tokens <= 5``). gpt-4o input is $2.5/1M and output $10/1M, so one call
    costs about $0.00015 — a few of them cross the $0.0002 whole-task cap. The
    meter records the real $; this only drives the call. Returns the HTTP status."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    body = {"model": "gpt-4o",
            # A ~40-token prompt so one call is a meaningful fraction of the tiny
            # $0.0002 cap even with max_tokens capped at 5.
            "messages": [{"role": "user",
                          "content": "Reply with the single word ok. " * 6}],
            "max_tokens": 5}
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    return resp.status_code


def main():
    print("=== LOCAL-827 container [%s]  task=%s budget=$%s ===" % (LABEL, TASK, BUDGET),
          flush=True)
    print("PAID_API_LOG=%s  AUDIOURA_TASK_BUDGET_DIR=%s"
          % (os.environ.get("PAID_API_LOG"), os.environ.get("AUDIOURA_TASK_BUDGET_DIR")),
          flush=True)
    if paid_api_meter is not None:
        try:
            spent0 = paid_api_meter._meter_log_spent(TASK)
            print("meter-log spend for %s BEFORE this container: $%.6f"
                  % (TASK, spent0), flush=True)
        except Exception as e:
            print("could not read pre-run meter-log spend: %s" % e, flush=True)
    if not KEY:
        print("[LOCAL-827] no OPENAI_API_KEY in env — cannot make a live call", flush=True)
        return 3

    made = 0
    for i in range(1, MAX_CALLS + 1):
        try:
            status = _tiny_openai_call(i)
            made += 1
            print("  call %d: SENT  status=%s" % (i, status), flush=True)
        except TaskBudgetExceeded as e:
            print("  call %d: REFUSED by cap — %s" % (i, str(e)), flush=True)
            print("[LOCAL-827] whole-task cap fired after %d sent call(s) in this "
                  "container; the refused call never reached the network." % made,
                  flush=True)
            break
        except Exception as e:
            # A paid call can fail for non-budget reasons (rate limit, network);
            # the meter still records a $0 row. Keep going a couple times.
            print("  call %d: error (non-budget): %s" % (i, str(e)[:160]), flush=True)
        # Sleep just past the cap's 10 s re-read window so the NEXT call's budget
        # check reads a FRESH sum that includes this call (and any call another
        # container recorded meanwhile) — this is what lets the cap fire exactly
        # when the running total crosses the budget, not one stale window late.
        time.sleep(float(os.environ.get("LOCAL827_SLEEP", "11")))
    else:
        print("[LOCAL-827] made %d call(s) without the cap firing in this container "
              "(it may fire in the NEXT container once the shared log crosses the "
              "budget)." % made, flush=True)

    if paid_api_meter is not None:
        try:
            # Force a fresh read past the 10 s cache so the post-run total is exact.
            with paid_api_meter._meterlog_lock:
                paid_api_meter._meterlog_cap_cache.clear()
            spent1 = paid_api_meter._meter_log_spent(TASK)
            print("meter-log spend for %s AFTER this container:  $%.6f"
                  % (TASK, spent1), flush=True)
        except Exception as e:
            print("could not read post-run meter-log spend: %s" % e, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
