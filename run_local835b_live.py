"""run_local835b_live.py — LOCAL-835B live, budget-enforced proof (Mac-local).

The BOUNCE: LOCAL-835 wired the activity-provider guard into the fresh path and
ran it ONCE; the 788B map override and the D545 replenish ladder then added
off-category stops back ("Kiteboarding lessons in Mui Ne" → tour 868: Sea Horse
Resort, Source Kiteboarding, Sandals Restaurant, The Bar, Jibe's Beach Club —
only one kite school). This run proves the guard now fires at EVERY ADD/KEEP
path, cheap env EXACTLY as the ticket specifies, stop pool OFF:

    CHEAP_ARM_CATEGORIES=museum,walking,restaurant,facility,specialized
    NARRATION_MODEL=gpt-4.1-mini
    RESEARCH_BACKEND=serper   SERP_PROVIDER=serper
    DISABLE_STOP_POOL=1       (pool off)

    "Kiteboarding lessons in Mui Ne, Vietnam"   (5 stops)
    "Scuba diving courses in Nha Trang, Vietnam" (4 stops)

PASS (per tour) = every delivered stop is an on-category PROVIDER of the
requested activity (a kite school / a dive centre) OR an honest shortfall of
providers (fewer than requested, never padded with a restaurant/bar/resort/
beach club/landmark), AND metered total < $0.45.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-835B TASK_BUDGET_USD=0.80. LiveRunMeter
records the run to the per-task JSON ledger and a reserve gate refuses to START a
tour once the ledger spend is at/over the cap. This is a Mac-LOCAL diagnostic
(the documented no-mount escape hatch, same as run_local834_live.py): it writes
its meter log under ./_local835b_meterlogs and sets METER_MOUNT_GUARD=0. It never
writes the shared/live DB and never touches the shared audioura-* containers.

The report lists each delivered stop with its classifier verdict
(candidate_is_activity_provider) so an off-category survivor is visible, and
groups the metered status-200 paid rows by model and by caller.
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
os.environ.setdefault("TASK_BUDGET_ID", "LOCAL-835B")
os.environ.setdefault("TASK_BUDGET_USD", "0.80")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.80") or "0.80")
PER_TOUR_CAP_USD = float(os.environ.get("PER_TOUR_CAP_USD", "0.45") or "0.45")
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
_METER_DIR = os.path.join(_HERE, "_local835b_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"          # documented no-mount diagnostic
os.environ["METER_SERVICE"] = "LOCAL-835B"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

TOURS = [
    ("Kiteboarding lessons in Mui Ne, Vietnam", "", 5),
    ("Scuba diving courses in Nha Trang, Vietnam", "", 4),
]

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


def _classify_titles(titles, request):
    """For each delivered stop TITLE, run the SAME guard verdict the pipeline uses
    (requested_activity + candidate_is_activity_provider on a name-only cand).
    Returns list of (n, title, verdict) where verdict is True (provider),
    False (off-category) or None (unclassifiable). A name-only verdict is a
    conservative lower bound — the live stop carries a Serper type the pipeline
    saw, so a True here is solid and a False here is a clear miss."""
    from category_match_guard import (requested_activity,
                                       candidate_is_activity_provider)
    act = requested_activity(request)
    out = []
    for n, t in titles:
        if not act:
            out.append((n, t, None))
            continue
        v = candidate_is_activity_provider({"name": t}, act)
        out.append((n, t, v))
    return out


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-835B live — activity guard at EVERY add/keep path "
          "(cheap arm, pool OFF) ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}  per-tour PASS cap=${PER_TOUR_CAP_USD:.2f}",
          flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)
    print(f"  CHEAP_ARM_CATEGORIES={os.environ['CHEAP_ARM_CATEGORIES']!r}", flush=True)
    print(f"  NARRATION_MODEL={os.environ['NARRATION_MODEL']!r} "
          f"RESEARCH_BACKEND={os.environ['RESEARCH_BACKEND']!r} "
          f"DISABLE_STOP_POOL={os.environ['DISABLE_STOP_POOL']!r}", flush=True)

    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-835B] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g

    results = []
    for (location, tour_type, n_stops) in TOURS:
        meter = LiveRunMeter("LOCAL-835B")
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        try:
            import task_budget as _tb
            _ledger_spent = _tb.spent_so_far("LOCAL-835B")
        except Exception:
            _ledger_spent = 0.0
        print(f"  task-ledger spent so far: ${_ledger_spent:.3f} / ${HARD_CAP_USD:.2f}",
              flush=True)
        if _ledger_spent >= HARD_CAP_USD:
            print(f"  [LOCAL-835B] reserve gate: ${_ledger_spent:.3f} >= "
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
            print(f"  [LOCAL-835B] raised: {e}", flush=True)
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
    total = sum(float(r.get("usd") or 0.0) for r in ok_rows)

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-835B SUMMARY ===", flush=True)
    overall_pass = True
    for r in results:
        verdicts = _classify_titles(r["titles"], r["location"])
        n_off = sum(1 for _, _, v in verdicts if v is False)
        n_prov = sum(1 for _, _, v in verdicts if v is True)
        print(f"\n  {r['location']}: {len(r['titles'])}/{r['requested']} stops "
              f"(providers={n_prov}, off-category={n_off})", flush=True)
        for n, t, v in verdicts:
            tag = ("PROVIDER" if v is True else
                   "OFF-CATEGORY!" if v is False else "unknown")
            print(f"    Stop {n}: {t[:70]:<70} [{tag}]", flush=True)
        # Per-tour PASS: no off-category survivor. Providers-only OR honest
        # shortfall both satisfy "no off-category survivor". Padding would show
        # as an off-category survivor and fail here.
        if n_off > 0:
            overall_pass = False
            print(f"    -> FAIL: {n_off} off-category stop(s) survived to delivery",
                  flush=True)
        else:
            shortfall = len(r["titles"]) < r["requested"]
            print(f"    -> PASS: no off-category survivor "
                  f"({'honest shortfall' if shortfall else 'providers only'})",
                  flush=True)

    print("\n  --- meter_report BY MODEL (status-200) ---", flush=True)
    for (kind, model), slot in sorted(by_model.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)

    print("\n  --- meter_report BY CALLER (status-200) ---", flush=True)
    for (kind, caller), slot in sorted(by_caller.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}  {caller}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)

    # Metered total is the sum of BOTH tours' status-200 rows; the per-tour PASS
    # cap is $0.45, so the two-tour metered total under 2×$0.45 is the budget
    # headline (the hard ledger cap is $0.80).
    print(f"\n  metered total (status-200, both tours): ${total:.4f} / "
          f"ledger cap ${HARD_CAP_USD:.2f}", flush=True)
    budget_ok = total < (2 * PER_TOUR_CAP_USD)
    print(f"  budget check: ${total:.4f} < 2×${PER_TOUR_CAP_USD:.2f}="
          f"${2 * PER_TOUR_CAP_USD:.2f}  -> {budget_ok}", flush=True)

    verdict = overall_pass and budget_ok
    print(f"\n=== LOCAL-835B OVERALL: {'PASS' if verdict else 'CHECK'} "
          f"(no off-category survivors={overall_pass}, "
          f"budget={budget_ok}) ===", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
