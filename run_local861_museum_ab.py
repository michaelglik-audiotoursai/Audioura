#!/usr/bin/env python3
"""run_local861_museum_ab.py — LOCAL-861 museum A/B (D754), budget-enforced.

Question: does gpt-4.1 narration make museum stories good enough to justify
~ +$0.40 per museum tour?

  Arm A (current): NARRATION_MODEL=gpt-4.1-mini, STORY_PASS_MODEL=gpt-4.1,
                   RESEARCH_BACKEND=serper                       (D746 env)
  Arm B          : identical except NARRATION_MODEL=gpt-4.1, museum only.

6 stops per museum, A then B per museum, same code, no DB (host mode, so every
DB-backed cache is cold by construction), DISABLE_TOUR_CACHE/DISABLE_STOP_POOL.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-861 TASK_BUDGET_USD=8.50, meter contract,
OWN meter dir ./_local861_meterlogs (D753 Mac-local no-mount escape hatch:
METER_MOUNT_GUARD=0 — never writes the shared/live DB, never touches the shared
audioura-* containers). If a run would exceed the cap the harness stops and
reports what ran. The cap is never raised.

Usage:  python3 run_local861_museum_ab.py [museum_key ...]    (default: all six)
Raw (arm-labelled) outputs go to ./_local861_raw/ (NOT committed); the blind
step (blind_local861.py) copies them to random ids.
"""
import contextlib
import io
import json
import os
import sys
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))
sys.path.insert(0, _HERE)


def _load_dotenv():
    try:
        with open(os.path.join(_HERE, ".env"), "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

CAP_USD = 8.50
os.environ["TASK_BUDGET_ID"] = "LOCAL-861"
os.environ["TASK_BUDGET_USD"] = "8.50"           # fixed: the cap is never raised
# Per-run ceiling (the whole-task ledger is the real authority).
os.environ["TEST_GEMINI_MAX_USD"] = "2.00"
os.environ["COST_HARD_LIMIT_USD"] = "2.00"

os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ["ARTIST_LIFE_CACHE_DISABLE"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
# Host mode = no DB: venue/works/thin-verify/tour caches are all DB-backed.
for _k in ("DATABASE_URL", "VENUE_CACHE_DB_URL"):
    os.environ.pop(_k, None)

_METER_DIR = os.path.join(_HERE, "_local861_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
os.environ["PAID_API_LOG"] = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-861"
os.environ["AUDIOURA_TASK_BUDGET_DIR"] = _METER_DIR

RAW = os.path.join(_HERE, "_local861_raw")
os.makedirs(RAW, exist_ok=True)

MUSEUMS = {
    "orsay": "Musée d'Orsay, Paris, France",
    "rijks": "Rijksmuseum, Amsterdam, Netherlands",
    "mfa": "Museum of Fine Arts, Boston, MA",
    "gardner": "Isabella Stewart Gardner Museum, Boston, MA",
    "lascaris": "Palais Lascaris, Nice, France",
    "asian": "Asian Art Museum, San Francisco, CA",
}
ARMS = {"A": "gpt-4.1-mini", "B": "gpt-4.1"}
STOPS = 6


class _Tee:
    def __init__(self, *s):
        self._s = s

    def write(self, d):
        for s in self._s:
            s.write(d)
        return len(d)

    def flush(self):
        for s in self._s:
            try:
                s.flush()
            except Exception:
                pass


def _spent():
    import task_budget as tb
    return float(tb.spent_so_far("LOCAL-861"))


def run_one(key, arm):
    import generate_tour_text as g
    from live_run_meter import LiveRunMeter
    loc = MUSEUMS[key]
    os.environ["NARRATION_MODEL"] = ARMS[arm]
    tag = f"{key}_{arm}"
    print(f"\n[RUN {tag}] {loc}  NARRATION_MODEL={ARMS[arm]}  ledger=${_spent():.4f}/{CAP_USD}", flush=True)
    meter = LiveRunMeter("LOCAL-861")   # refuses to start when the ledger is exhausted
    buf = io.StringIO()
    text, err = None, None
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(loc, "museum", None, STOPS)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    secs = time.time() - t0
    try:
        meter.add_generation(g)
    except Exception:
        pass
    try:
        meter.record()
    except Exception as e:  # noqa: BLE001
        print(f"  meter.record failed: {e}", flush=True)
    usd = None
    try:
        usd = float(meter.total_usd())
    except Exception:
        pass
    try:
        meter.uninstall()
    except Exception:
        pass
    with open(os.path.join(RAW, f"{tag}.txt"), "w", encoding="utf-8") as f:
        f.write(text or "")
    with open(os.path.join(RAW, f"{tag}.log"), "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    with open(os.path.join(RAW, f"{tag}.meta.json"), "w", encoding="utf-8") as f:
        json.dump({"museum": key, "location": loc, "arm": arm, "narration_model": ARMS[arm],
                   "seconds": round(secs, 1), "usd_meter": usd, "ledger_after": round(_spent(), 4),
                   "error": err, "chars": len(text or "")}, f, indent=2)
    print(f"[DONE {tag}] {secs:.0f}s  usd={usd}  ledger=${_spent():.4f}/{CAP_USD}  err={err}", flush=True)
    return usd, err


def main():
    keys = sys.argv[1:] or list(MUSEUMS)
    last = {"A": 0.9, "B": 1.4}          # conservative pre-run estimates until measured
    for key in keys:
        for arm in os.environ.get("ARMS_ONLY", "AB"):
            if os.path.exists(os.path.join(RAW, f"{key}_{arm}.meta.json")):
                print(f"[SKIP {key}_{arm}] already ran", flush=True)
                continue
            # Arm-B runs are the expensive ones: serialise them across driver
            # processes (file lock) so the ledger check always sees prior spend.
            lock = None
            if arm == "B":
                import fcntl
                lock = open(os.path.join(_METER_DIR, "armB.lock"), "w")
                fcntl.flock(lock, fcntl.LOCK_EX)
            if _spent() + last[arm] > CAP_USD:
                print(f"[STOP] ledger ${_spent():.2f} + est ${last[arm]:.2f} > cap ${CAP_USD} — "
                      f"not starting {key}_{arm}", flush=True)
                return 3
            try:
                usd, err = run_one(key, arm)
            except Exception as e:  # BudgetExceeded etc.
                print(f"[STOP] {key}_{arm}: {type(e).__name__}: {e}", flush=True)
                return 3
            finally:
                if lock:
                    lock.close()
            if usd:
                last[arm] = max(usd * 1.15, 0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
