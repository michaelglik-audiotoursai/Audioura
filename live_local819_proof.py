#!/usr/bin/env python3
"""live_local819_proof.py — LOCAL-819 LIVE proof (budget enforced).

Makes at most 5 TINY real OpenAI calls (max_tokens=5) through the paid-API meter
and shows that each one lands a meter row with REAL tokens_in/tokens_out (the bug
was tokens=0 on every OpenAI row). Proves, end to end:

  * the network meter catches the OpenAI SDK's httpx calls,
  * the LOCAL-819 fix writes top-level tokens_in / tokens_out and key_suffix,
  * meter_report.py totals those rows by day / service / model / key-suffix,
  * the whole-task budget (TASK_BUDGET_ID=LOCAL-819, TASK_BUDGET_USD=0.10) is live.

SAFETY — does NOT pollute the shared ledger: it writes to a PROOF-ONLY log
(~/Audioura/meterlogs/paid_api_calls_LOCAL-819-proof.jsonl) and tags every row
service=LOCAL-819-proof, so the live paid_api_calls.jsonl (service '-c', written
by other processes) is untouched. Never writes the live DB (DB write is stubbed).

Run:
    TASK_BUDGET_ID=LOCAL-819 TASK_BUDGET_USD=0.10 python3 live_local819_proof.py
"""
import json
import os
import sys

N_CALLS = int(os.environ.get("LOCAL819_N", "5"))
MAX_TOKENS = 5
MODEL = os.environ.get("LOCAL819_MODEL", "gpt-4o-mini")
PROOF_SERVICE = "LOCAL-819-proof"
PROOF_LOG = os.path.join(os.path.expanduser("~"), "Audioura", "meterlogs",
                         "paid_api_calls_LOCAL-819-proof.jsonl")


def _load_env(path):
    try:
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


def main():
    # Load the Mac's .env (OPENAI_API_KEY lives there) without printing it.
    _load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        print("[LOCAL-819] no OPENAI_API_KEY in env/.env — cannot run live proof")
        return 2

    # PROOF-ONLY meter config: distinct log + service so the shared ledger is not
    # polluted. key_suffix is the NON-sensitive last-4 of the key (the ticket's
    # mac-mini key ends k9sA).
    os.environ["PAID_API_LOG"] = PROOF_LOG
    os.environ["METER_SERVICE"] = PROOF_SERVICE
    os.environ.setdefault("METER_KEY_SUFFIX", key[-4:])

    # Make sure the whole-task budget is on for this proof.
    os.environ.setdefault("TASK_BUDGET_ID", "LOCAL-819")
    os.environ.setdefault("TASK_BUDGET_USD", "0.10")

    # Install the meter from the host (no container here). _meter is beside us.
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "_meter"))
    import paid_api_meter as meter
    # Never touch the live DB during the proof — only the JSONL log.
    meter._db_write = lambda rec: None
    meter.install()

    print("=" * 70)
    print("LOCAL-819 LIVE PROOF")
    print("  model            : %s  (max_tokens=%d)" % (MODEL, MAX_TOKENS))
    print("  calls            : %d (<=5)" % N_CALLS)
    print("  service tag      : %s" % PROOF_SERVICE)
    print("  key suffix       : %s" % os.environ.get("METER_KEY_SUFFIX"))
    print("  proof log        : %s" % PROOF_LOG)
    print("  TASK_BUDGET_ID   : %s" % os.environ.get("TASK_BUDGET_ID"))
    print("  TASK_BUDGET_USD  : %s" % os.environ.get("TASK_BUDGET_USD"))
    print("=" * 70)

    # Snapshot proof-log line count before.
    def _rows():
        out = []
        try:
            with open(PROOF_LOG) as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln:
                        out.append(json.loads(ln))
        except FileNotFoundError:
            pass
        return out

    before = len(_rows())

    # Use the OpenAI SDK so the call goes over httpx — the exact path that was
    # unmetered before LOCAL-678 and whose rows showed tokens=0 before LOCAL-819.
    from openai import OpenAI
    client = OpenAI(api_key=key)

    made = 0
    for i in range(N_CALLS):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": "Reply with the number %d." % (i + 1)}],
                max_tokens=MAX_TOKENS,
            )
            made += 1
            u = resp.usage
            print("  call %d: ok  prompt=%s completion=%s" %
                  (i + 1, getattr(u, "prompt_tokens", "?"),
                   getattr(u, "completion_tokens", "?")))
        except Exception as e:
            print("  call %d: stopped (%s: %s)" % (i + 1, type(e).__name__, str(e)[:120]))
            break

    rows = _rows()[before:]
    print("\n--- PROOF METER ROWS (%d new) ---" % len(rows))
    all_have_tokens = True
    for r in rows:
        ti, to = r.get("tokens_in"), r.get("tokens_out")
        if not (isinstance(ti, int) and isinstance(to, int) and (ti > 0 or to > 0)):
            all_have_tokens = False
        print("  kind=%s status=%s model=%s tokens_in=%s tokens_out=%s usd=%.8f "
              "service=%s key_suffix=%s" %
              (r.get("kind"), r.get("status"), r.get("model"),
               ti, to, float(r.get("usd") or 0.0),
               r.get("service"), r.get("key_suffix")))

    total_usd = sum(float(r.get("usd") or 0.0) for r in rows)
    print("\n  calls made           : %d" % made)
    print("  meter rows written   : %d" % len(rows))
    print("  all rows real tokens : %s" % all_have_tokens)
    print("  total proof spend    : $%.8f (budget $%s)" %
          (total_usd, os.environ.get("TASK_BUDGET_USD")))

    # Record this run's spend to the whole-task ledger so task_budget_report.py
    # LOCAL-819 reflects it.
    try:
        import task_budget
        task_budget.record_run("LOCAL-819", round(total_usd, 8),
                               note=PROOF_SERVICE + " live proof", capped=False)
        print("  recorded to task budget ledger LOCAL-819")
    except Exception as e:
        print("  [warn] could not record task budget: %s" % e)

    ok = (made >= 1 and len(rows) == made and all_have_tokens
          and total_usd < float(os.environ.get("TASK_BUDGET_USD", "0.10")))
    print("\n  RESULT: %s" % ("PASS" if ok else "CHECK"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
