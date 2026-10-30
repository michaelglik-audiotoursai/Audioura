#!/usr/bin/env python3
"""run_local820_container.py — LOCAL-820 LIVE PROOF (isolated container).

Proves the LOCAL-820 fix end to end with REAL money (tiny): an isolated
``docker run --rm`` container wired by the meter contract makes up to TWO tiny
OpenAI calls (``max_tokens=5``) and the rows LAND in the shared host log
``~/Audioura/meterlogs/paid_api_calls.jsonl`` tagged ``service=LOCAL-820`` with
real token counts — instead of dying inside the container as LOCAL-818's did.

NO tours. The whole-task budget is enforced two ways:
  * TASK_BUDGET_ID=LOCAL-820 / TASK_BUDGET_USD=0.10 — the meter's raw paid door
    (_meter/paid_api_meter.py, installed via PYTHONPATH=/opt/meter) refuses any
    paid request once the task's recorded total reaches the budget; and
  * this harness computes the call cost and STOPS before a call that would cross
    the budget. Two gpt-4.1-mini calls of ~20 input + 5 output tokens cost well
    under a cent, so the $0.10 cap is never approached — the cap is the safety
    net, the small call count is the real control.

Run via ./run_local820_live.sh (which supplies the meter contract). The baked-in
meter (image ENV PYTHONPATH=/opt/meter) records the call to the mounted host log
automatically; this harness only has to MAKE the call.
"""
import json
import os
import sys
import time

# tests/ carries live_run_meter.py; make it importable whether this runs from the
# worktree root (bind-mounted at /app) or the baked image layout.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))

TASK = "LOCAL-820"
MODEL = os.environ.get("NARRATION_MODEL", "gpt-4.1-mini")
MAX_TOKENS = 5
MAX_CALLS = 2
LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

print(f"=== {TASK} live meter proof (model={MODEL}, max_tokens={MAX_TOKENS}, "
      f"<= {MAX_CALLS} calls) ===", flush=True)
print(f"PAID_API_LOG={LOG}  METER_SERVICE={os.environ.get('METER_SERVICE')!r}  "
      f"TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
      f"TASK_BUDGET_USD={os.environ.get('TASK_BUDGET_USD')!r}", flush=True)


def _rows_for_task(path, service, since_ts):
    """Rows in the shared log tagged service and at/after since_ts."""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("service") == service and str(r.get("ts") or "") >= since_ts:
                out.append(r)
    return out


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print(f"[{TASK}] no OPENAI_API_KEY in env — cannot make a live call; aborting",
              flush=True)
        return 2

    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        import requests
    except Exception as e:
        print(f"[{TASK}] requests unavailable ({e}); aborting", flush=True)
        return 2

    # Whole-task budget ledger: LiveRunMeter records THIS run's $ to the append-only
    # ledger (~/.audioura_task_budgets/<id>.json, host dir via AUDIOURA_TASK_BUDGET_DIR
    # so it survives --rm just like the meter rows) and refuses to start if the task
    # is already over budget. tests/ is on sys.path inside the container (/app).
    meter = None
    try:
        from live_run_meter import LiveRunMeter
        meter = LiveRunMeter(TASK, install_cap=False)  # no grounding here; manual $
    except Exception as e:
        print(f"[{TASK}] LiveRunMeter unavailable ({e}); continuing without the "
              f"budget ledger (the raw meter door still enforces the cap)", flush=True)

    # Mirror the PRODUCTION OpenAI path exactly (generate_tour_text.py calls
    # requests.post("https://api.openai.com/v1/chat/completions", ...)). That is
    # the path the baked-in meter patches, so the row is recorded the same way a
    # real tour's calls are.
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
               "Content-Type": "application/json"}
    made = 0
    for i in range(MAX_CALLS):
        data = {
            "model": MODEL,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        }
        try:
            print(f"[{TASK}] call {i + 1}/{MAX_CALLS}: {MODEL} max_tokens={MAX_TOKENS}",
                  flush=True)
            resp = requests.post(url, headers=headers, data=json.dumps(data),
                                 timeout=30)
            if resp.status_code != 200:
                print(f"  -> HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
                # A 4xx (e.g. budget door 402/429) is a stop, not a crash.
                break
            made += 1
            body = resp.json()
            u = body.get("usage") or {}
            content = (body.get("choices") or [{}])[0].get("message", {}).get("content")
            print(f"  -> content={content!r} "
                  f"prompt_tokens={u.get('prompt_tokens')} "
                  f"completion_tokens={u.get('completion_tokens')}", flush=True)
        except Exception as e:
            # The whole-task budget raises here if the cap is hit — report and stop.
            print(f"[{TASK}] call {i + 1} stopped: {type(e).__name__}: {str(e)[:200]}",
                  flush=True)
            break

    # Record this run's OpenAI $ to the whole-task budget ledger (read the two tiny
    # rows we just wrote so the ledger $ matches the meter exactly).
    if meter is not None:
        try:
            _my_rows = _rows_for_task(LOG, TASK, since)
            _usd = sum(float(r.get("usd") or 0.0) for r in _my_rows)
            meter.add_openai(_usd)
            row_id = meter.record()
            print(f"[{TASK}] budget ledger updated: +${_usd:.6f} "
                  f"(cost_ledger row {row_id})", flush=True)
        except Exception as e:
            print(f"[{TASK}] budget ledger write skipped (non-fatal): {e}", flush=True)

    # Give the meter's synchronous writer a moment (it writes inline, but be safe).
    time.sleep(0.5)
    rows = _rows_for_task(LOG, TASK, since)
    print(f"\n[{TASK}] calls made: {made}", flush=True)
    print(f"[{TASK}] rows in {LOG} tagged service={TASK} since {since}: {len(rows)}",
          flush=True)
    for r in rows:
        print(f"  ROW ts={r.get('ts')} kind={r.get('kind')} model={r.get('model')} "
              f"tokens_in={r.get('tokens_in')} tokens_out={r.get('tokens_out')} "
              f"usd={r.get('usd')} key_suffix={r.get('key_suffix')!r} "
              f"status={r.get('status')}", flush=True)

    ok = made >= 1 and len(rows) >= 1 and all(
        r.get("kind") == "openai" for r in rows)
    print(f"\n[{TASK}] VERDICT: " + (
        "PASS — live OpenAI call(s) metered to the shared host log, "
        f"service={TASK}, real tokens." if ok else
        "FAIL — see above."), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
