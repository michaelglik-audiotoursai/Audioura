"""run_local847_live.py — LOCAL-847 live, budget-enforced proof (Mac-local).

The ticket request REFUSED in the field (request 68ce1fe4, GCloud_Storied wave 18
proof, gen 00023-9zz @ 2532fc1c, cheap env):

    "Kiteboarding schools in Mui Ne beach area, Vietnam" (5)
        → "We could not find enough verified material…"

Two fixes proven live, cheap env, stop pool OFF:

  (1) SCOPE — the generic AREA/FEATURE phrase "Mui Ne beach area" is widened to
      the town "Mui Ne" (LOCAL-843 only stripped the single word "beach"), and
      the scope geocode falls back to the next comma segment if the full scope
      still fails — so provider discovery scopes to the Mui Ne ward and does not
      refuse "no in-scope places".

  (2) MIXED VENUES — a kite school that also has a bar ("Kitesurfing Mui Ne -
      Surf Bar", "Dive & Dine") is kept as a provider; only a venue whose name
      AND type lack the activity ("Kite Bar", "Blue Sky Restaurant") is dropped.

PASS = >= 4 providers delivered, Gemini $0, metered total <= $0.30.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-847 TASK_BUDGET_USD=0.40. LiveRunMeter
records to a per-task JSON ledger and a reserve gate refuses to START the tour
once the ledger spend is at/over the cap. Mac-LOCAL diagnostic (the documented
no-mount escape hatch, as run_local845_live.py): writes its meter log under
./_local847_meterlogs, METER_MOUNT_GUARD=0. It never writes the shared/live DB
and never touches the shared audioura-* containers.
"""
import contextlib
import io
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))

# ── budget + cheap env (ticket-exact) ────────────────────────────────────────
os.environ.setdefault("TASK_BUDGET_ID", "LOCAL-847")
os.environ.setdefault("TASK_BUDGET_USD", "0.40")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.40") or "0.40")
PER_TOUR_CAP_USD = float(os.environ.get("PER_TOUR_CAP_USD", "0.30") or "0.30")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")

_METER_DIR = os.path.join(_HERE, "_local847_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-847"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

TOURS = [
    ("Kiteboarding schools in Mui Ne beach area, Vietnam", "", 5),
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
# A delivered stop is a PROVIDER unless its name is purely a food/leisure venue.
_FOOD_WORDS = ("restaurant", "cafe", "café", "bistro", "eatery",
               "nhà hàng", "nha hang", "quán", "quan", "seafood", "coffee")
_PROVIDER_HINT = ("kite", "surf", "kiteboard", "dive", "school", "club",
                  "centre", "center", "sports", "station", "academy")


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
    print("=== LOCAL-847 live — area-scope widening + mixed-venue provider "
          "(cheap arm, pool OFF) ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}  per-tour cap=${PER_TOUR_CAP_USD:.2f}",
          flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)
    print(f"  CHEAP_ARM_CATEGORIES={os.environ['CHEAP_ARM_CATEGORIES']!r} "
          f"STORY_PASS_MODEL={os.environ['STORY_PASS_MODEL']!r} "
          f"NARRATION_MODEL={os.environ['NARRATION_MODEL']!r} "
          f"DISABLE_STOP_POOL={os.environ['DISABLE_STOP_POOL']!r}", flush=True)

    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-847] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g

    results = []
    for (location, tour_type, n_stops) in TOURS:
        meter = LiveRunMeter("LOCAL-847")
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        try:
            import task_budget as _tb
            _ledger_spent = _tb.spent_so_far("LOCAL-847")
        except Exception:
            _ledger_spent = 0.0
        print(f"  task-ledger spent so far: ${_ledger_spent:.3f} / ${HARD_CAP_USD:.2f}",
              flush=True)
        if _ledger_spent >= HARD_CAP_USD:
            print(f"  [LOCAL-847] reserve gate: ${_ledger_spent:.3f} >= "
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
            print(f"  [LOCAL-847] raised: {e}", flush=True)
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

        refused = bool(re.search(r"could not find enough verified", text or "",
                                 re.IGNORECASE))
        results.append({"location": location, "requested": n_stops,
                        "titles": titles, "text": text or "", "refused": refused})

    # ── REPORT ────────────────────────────────────────────────────────────────
    rows = _meter_rows()
    ok_rows = [r for r in rows if _ok(r)]
    by_model = _group(rows, lambda r: (r.get("kind") or "?", r.get("model") or "?"))
    total = sum(float(r.get("usd") or 0.0) for r in ok_rows)
    gemini_usd = sum(float(r.get("usd") or 0.0) for r in ok_rows
                     if "gemini" in (str(r.get("model") or "")).lower()
                     or "gemini" in (str(r.get("kind") or "")).lower())

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-847 SUMMARY ===", flush=True)
    overall_pass = True

    for r in results:
        print(f"\n  {r['location']}: {len(r['titles'])}/{r['requested']} stops "
              f"(refused={r['refused']})", flush=True)
        for n, t in r["titles"]:
            print(f"    Stop {n}: {t[:72]}", flush=True)

        if r["refused"]:
            overall_pass = False
            print("    -> FAIL: tour REFUSED (no scope / not enough material)",
                  flush=True)
            continue

        # Count providers: a delivered stop that is NOT a pure food venue.
        providers = []
        for _n, t in r["titles"]:
            tl = t.lower()
            is_food = any(w in tl for w in _FOOD_WORDS)
            has_hint = any(w in tl for w in _PROVIDER_HINT)
            # A food-named stop with no provider hint is NOT a provider.
            if is_food and not has_hint:
                continue
            providers.append(t)
        print(f"    providers delivered: {len(providers)} "
              f"-> {[p[:40] for p in providers]}", flush=True)
        if len(providers) >= 4:
            print(f"    -> PASS: {len(providers)} providers (>= 4)", flush=True)
        else:
            overall_pass = False
            print(f"    -> FAIL: only {len(providers)} providers (< 4)", flush=True)

    print("\n  --- meter_report BY MODEL (status-200) ---", flush=True)
    for (kind, model), slot in sorted(by_model.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)

    print(f"\n  Gemini spend: ${gemini_usd:.4f}  (PASS requires $0)", flush=True)
    print(f"  metered total (status-200): ${total:.4f} / ledger cap "
          f"${HARD_CAP_USD:.2f} / per-tour PASS cap ${PER_TOUR_CAP_USD:.2f}",
          flush=True)
    gemini_ok = gemini_usd <= 1e-9
    budget_ok = total <= PER_TOUR_CAP_USD and total < HARD_CAP_USD
    print(f"  gemini check: ${gemini_usd:.4f} == $0 -> {gemini_ok}", flush=True)
    print(f"  budget check: ${total:.4f} <= ${PER_TOUR_CAP_USD:.2f} -> {budget_ok}",
          flush=True)

    verdict = overall_pass and budget_ok and gemini_ok
    print(f"\n=== LOCAL-847 OVERALL: {'PASS' if verdict else 'CHECK'} "
          f"(providers={overall_pass}, gemini={gemini_ok}, budget={budget_ok}) ===",
          flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
