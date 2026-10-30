"""run_local834_live.py — LOCAL-834 live, budget-enforced proof (Mac-local).

ONE tour, cheap env EXACTLY as the ticket specifies, stop pool OFF:

    CHEAP_ARM_CATEGORIES=museum,walking,restaurant,facility,specialized
    NARRATION_MODEL=gpt-4.1-mini
    RESEARCH_BACKEND=serper   SERP_PROVIDER=serper

    "Kitesurfing schools in Mui Ne, Vietnam"  (5 stops)

PASS = 5/5 kite schools, Gemini $0 (or each remaining Gemini call justified),
total < $0.40.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-834 TASK_BUDGET_USD=0.60. LiveRunMeter
records the run to the per-task JSON ledger and a reserve gate refuses to START
once the ledger spend is at/over the cap. TEST_GEMINI_MAX_USD caps the combined
running spend at the grounding counter.

This is a Mac-LOCAL diagnostic (no shared container, no bind mount): it writes its
meter log under ./_local834_meterlogs and sets METER_MOUNT_GUARD=0, which is the
documented escape hatch for a deliberate no-mount run (paid_api_meter.check_meter_
mount). It never writes the shared/live DB.

The report groups the metered, status-200 paid rows BY MODEL and BY CALLER
(filename:lineno — the meter's own `caller` field), so any remaining Gemini call
is attributed to the exact line that issued it.
"""
import io
import json
import os
import re
import sys
import time
import contextlib

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))

# ── budget + cheap env (ticket-exact) ────────────────────────────────────────
os.environ.setdefault("TASK_BUDGET_ID", "LOCAL-834")
os.environ.setdefault("TASK_BUDGET_USD", "0.60")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.60") or "0.60")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")

# Local meter log + task-budget ledger (Mac-local, no bind mount).
_METER_DIR = os.path.join(_HERE, "_local834_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"          # documented no-mount diagnostic
os.environ["METER_SERVICE"] = "LOCAL-834"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

TOURS = [("Kitesurfing schools in Mui Ne, Vietnam", "", 5)]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")


def _meter_rows():
    rows = []
    try:
        with open(METER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    return rows


def _ok(r):
    return r.get("status") in (200, "200")


def _group(rows, keyfn):
    out = {}
    for r in rows:
        if not _ok(r):
            continue
        slot = out.setdefault(keyfn(r), {"calls": 0, "usd": 0.0})
        slot["calls"] += 1
        try:
            slot["usd"] += float(r.get("usd") or 0.0)
        except (TypeError, ValueError):
            pass
    return out


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-834 live — places/business path must honour RESEARCH_BACKEND "
          "(cheap arm, pool OFF) ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}  meter log: {METER_LOG}", flush=True)
    print(f"  CHEAP_ARM_CATEGORIES={os.environ['CHEAP_ARM_CATEGORIES']!r}", flush=True)
    print(f"  NARRATION_MODEL={os.environ['NARRATION_MODEL']!r} "
          f"RESEARCH_BACKEND={os.environ['RESEARCH_BACKEND']!r} "
          f"DISABLE_STOP_POOL={os.environ['DISABLE_STOP_POOL']!r}", flush=True)

    # fresh meter log for this run
    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-834] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g

    results = []
    for (location, tour_type, n_stops) in TOURS:
        meter = LiveRunMeter("LOCAL-834")
        try:
            spent = meter.total_usd()
        except Exception:
            spent = 0.0
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        try:
            import task_budget as _tb
            _ledger_spent = _tb.spent_so_far("LOCAL-834")
        except Exception:
            _ledger_spent = 0.0
        print(f"  task-ledger spent so far: ${_ledger_spent:.3f} / ${HARD_CAP_USD:.2f}",
              flush=True)
        if _ledger_spent >= HARD_CAP_USD:
            print(f"  [LOCAL-834] reserve gate: ${_ledger_spent:.3f} >= "
                  f"${HARD_CAP_USD} — NOT running", flush=True)
            try:
                meter.uninstall()
            except Exception:
                pass
            break

        t0 = time.time()
        text = None
        buf = io.StringIO()

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

        try:
            with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
                text, _out, _coords = g.generate_tour_text(
                    location, tour_type, None, n_stops)
            dt = time.time() - t0
            titles = [(int(a), b.strip())
                      for a, b in _STOP_HEADER_RE.findall(text or "")]
            print(f"  generated in {dt:.0f}s — {len(titles)} stops", flush=True)
        except Exception as e:
            import traceback
            print(f"  [LOCAL-834] raised: {e}", flush=True)
            traceback.print_exc()
            titles = []
        finally:
            for fn in ("add_generation", "record"):
                try:
                    (meter.add_generation(g) if fn == "add_generation"
                     else meter.record())
                except Exception:
                    pass
            try:
                print("  " + meter.summary().replace("\n", "\n  "), flush=True)
            except Exception:
                pass
            try:
                meter.uninstall()
            except Exception:
                pass

        results.append({"location": location, "requested": n_stops,
                        "titles": titles, "text": text or ""})

    # ── REPORT ────────────────────────────────────────────────────────────────
    rows = _meter_rows()
    ok_rows = [r for r in rows if _ok(r)]
    by_model = _group(rows, lambda r: (r.get("kind") or "?", r.get("model") or "?"))
    by_caller = _group(rows, lambda r: (r.get("kind") or "?", r.get("caller") or "?"))
    gemini_rows = [r for r in ok_rows if (r.get("kind") == "gemini")]
    gemini_usd = sum(float(r.get("usd") or 0.0) for r in gemini_rows)
    total = sum(float(r.get("usd") or 0.0) for r in ok_rows)

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-834 SUMMARY ===", flush=True)
    for r in results:
        print(f"\n  {r['location']}: {len(r['titles'])}/{r['requested']} stops",
              flush=True)
        for n, t in r["titles"]:
            print(f"    Stop {n}: {t[:80]}", flush=True)

    print("\n  --- meter_report BY MODEL (status-200) ---", flush=True)
    for (kind, model), slot in sorted(by_model.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)

    print("\n  --- meter_report BY CALLER (status-200) ---", flush=True)
    for (kind, caller), slot in sorted(by_caller.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}  {caller}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)

    n_stops_ok = results and len(results[0]["titles"]) == results[0]["requested"]
    print(f"\n  Gemini spend: ${gemini_usd:.4f}  ({len(gemini_rows)} status-200 "
          f"gemini rows)", flush=True)
    print(f"  metered total (status-200): ${total:.4f} / cap ${HARD_CAP_USD:.2f}",
          flush=True)
    verdict = (n_stops_ok and gemini_usd == 0.0 and total < 0.40)
    print(f"\n=== LOCAL-834 OVERALL: {'PASS' if verdict else 'CHECK'} "
          f"(5/5={bool(n_stops_ok)}, gemini=${gemini_usd:.4f}, "
          f"total=${total:.4f}<$0.40={total < 0.40}) ===", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
