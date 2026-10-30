#!/usr/bin/env python3
"""run_local822_container.py — the TINY in-container probe for LOCAL-822 / 822B.

Makes exactly ONE paid OpenAI call with max_tokens<=5, through the network meter
installed by PYTHONPATH=/opt/meter. The live runs prove the container meter-mount
guard (LOCAL-822), scoped to TASK RUNS ONLY (LOCAL-822B), is mechanical:

  * TASK RUN WITHOUT the meterlogs bind-mount -> paid_api_meter.check_meter_mount
    raises MeterMountMissing BEFORE the request is sent. $0 spent, no row.
  * TASK RUN WITH the full contract (bind-mount + METER_SERVICE=LOCAL-822B) -> the
    call goes out and ONE row lands in ~/Audioura/meterlogs/paid_api_calls.jsonl
    with service=LOCAL-822B.
  * PRODUCTION (K_SERVICE set, no task id, no mount) -> the guard is NOT armed, so
    the paid call GOES THROUGH — the guard can never refuse a production call.

Run inside audioura-tour-generator:latest with the meter on PYTHONPATH. Prints a
single line the wrapper greps. Never a full tour; the cheapest possible paid call.
"""
import os
import sys

# The meter installs via sitecustomize when PYTHONPATH=/opt/meter. Import it
# explicitly too so we can name its exception and force install() in case
# sitecustomize did not run.
sys.path.insert(0, "/opt/meter")
import paid_api_meter  # noqa: E402

paid_api_meter.install()

import requests  # noqa: E402

API_KEY = os.environ.get("OPENAI_API_KEY") or ""
URL = "https://api.openai.com/v1/chat/completions"
PAYLOAD = {
    "model": "gpt-4o-mini",
    "max_tokens": 5,                       # <= 5 per the ticket
    "messages": [{"role": "user", "content": "hi"}],
}


def main():
    if not API_KEY:
        print("LOCAL822_PROBE: NO_API_KEY (cannot make the paid call)")
        return 3
    headers = {"Authorization": "Bearer " + API_KEY,
               "Content-Type": "application/json"}
    try:
        resp = requests.post(URL, json=PAYLOAD, headers=headers, timeout=30)
    except paid_api_meter.MeterMountMissing as e:
        print("LOCAL822_PROBE: REFUSED_BY_MOUNT_GUARD: %s" % (str(e)[:300],))
        return 0
    except paid_api_meter.TaskBudgetExceeded as e:
        print("LOCAL822_PROBE: REFUSED_BY_TASK_BUDGET: %s" % (str(e)[:200],))
        return 0
    except paid_api_meter.DailyPaidLimitExceeded as e:
        print("LOCAL822_PROBE: REFUSED_BY_DAILY_LIMIT: %s" % (str(e)[:200],))
        return 0
    print("LOCAL822_PROBE: CALL_SENT status=%s" % (resp.status_code,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
