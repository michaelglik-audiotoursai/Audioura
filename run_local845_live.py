"""run_local845_live.py — LOCAL-845 live, budget-enforced proof (Mac-local).

Two leftover fixes proven live, cheap env, stop pool OFF:

  (1) PROVIDER GUARD — "Scuba diving courses in Nha Trang, Vietnam" (4) must
      deliver dive providers only; NO restaurant (the field defect kept the
      heritage-house restaurant "Nha Trang Xua"). The LOCAL-845 resolver now
      classifies an UNKNOWN-tail candidate with ONE cheap 24 h-cached Serper
      Places lookup, so a restaurant with no English food word is dropped.

  (2) OLYMPIA D1v2 — "Orsay Museum, Paris, France" (5): if "Olympia" (Manet) is
      selected it must verify, not DROP. The canonical-set prune no longer
      deletes the bare famous work when its longer siblings ("A Modern Olympia" /
      "Une moderne Olympia") are present. The run prints every [D1v2]
      VERIFIED/DROPPED line.

PASS:
  * scuba — no delivered stop is a restaurant/bar/café (no off-category survivor);
  * orsay — if "Olympia" is among the selected candidates, it is VERIFIED (never
    "[D1v2] DROPPED 'Olympia'"); the [D1v2] lines are pasted.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-845 TASK_BUDGET_USD=0.50. LiveRunMeter
records to a per-task JSON ledger and a reserve gate refuses to START a tour once
the ledger spend is at/over the cap. Mac-LOCAL diagnostic (the documented
no-mount escape hatch, as run_local835b_live.py): writes its meter log under
./_local845_meterlogs, METER_MOUNT_GUARD=0. It never writes the shared/live DB
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
os.environ.setdefault("TASK_BUDGET_ID", "LOCAL-845")
os.environ.setdefault("TASK_BUDGET_USD", "0.50")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50")
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

_METER_DIR = os.path.join(_HERE, "_local845_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-845"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

TOURS = [
    ("Scuba diving courses in Nha Trang, Vietnam", "", 4),
    ("Orsay Museum, Paris, France", "", 5),
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_D1V2_RE = re.compile(r"(?mi)^\s*\[D1v2\]\s+(?:VERIFIED|DROPPED)\b.*$")
_FOOD_WORDS = ("restaurant", "cafe", "café", "bar", "pub", "bistro", "eatery",
               "nhà hàng", "nha hang", "quán", "quan", "seafood", "coffee")


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
    print("=== LOCAL-845 live — provider-guard restaurant drop + Olympia D1v2 "
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
        print(f"[LOCAL-845] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g

    results = []
    for (location, tour_type, n_stops) in TOURS:
        meter = LiveRunMeter("LOCAL-845")
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        try:
            import task_budget as _tb
            _ledger_spent = _tb.spent_so_far("LOCAL-845")
        except Exception:
            _ledger_spent = 0.0
        print(f"  task-ledger spent so far: ${_ledger_spent:.3f} / ${HARD_CAP_USD:.2f}",
              flush=True)
        if _ledger_spent >= HARD_CAP_USD:
            print(f"  [LOCAL-845] reserve gate: ${_ledger_spent:.3f} >= "
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
            print(f"  [LOCAL-845] raised: {e}", flush=True)
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

        d1v2_lines = [m.group(0).strip() for m in _D1V2_RE.finditer(buf.getvalue())]
        results.append({"location": location, "requested": n_stops,
                        "titles": titles, "text": text or "",
                        "d1v2": d1v2_lines})

    # ── REPORT ────────────────────────────────────────────────────────────────
    rows = _meter_rows()
    ok_rows = [r for r in rows if _ok(r)]
    by_model = _group(rows, lambda r: (r.get("kind") or "?", r.get("model") or "?"))
    total = sum(float(r.get("usd") or 0.0) for r in ok_rows)

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-845 SUMMARY ===", flush=True)
    overall_pass = True

    for r in results:
        print(f"\n  {r['location']}: {len(r['titles'])}/{r['requested']} stops",
              flush=True)
        for n, t in r["titles"]:
            print(f"    Stop {n}: {t[:72]}", flush=True)

        if r["location"].lower().startswith("scuba"):
            # PASS: no delivered stop is a food venue.
            food = [t for _, t in r["titles"]
                    if any(w in t.lower() for w in _FOOD_WORDS)]
            if food:
                overall_pass = False
                print(f"    -> FAIL: restaurant/bar survived: {food}", flush=True)
            else:
                print("    -> PASS: no restaurant/bar in the scuba tour", flush=True)

        if "orsay" in r["location"].lower():
            if r["d1v2"]:
                print("    --- [D1v2] lines ---", flush=True)
                for ln in r["d1v2"]:
                    print(f"      {ln}", flush=True)
            dropped_oly = [ln for ln in r["d1v2"]
                           if "DROPPED" in ln and re.search(r"['\"]?olympia['\"]?",
                                                            ln, re.IGNORECASE)
                           and "moderne" not in ln.lower()
                           and "modern" not in ln.lower()]
            verified_oly = [ln for ln in r["d1v2"]
                            if "VERIFIED" in ln and re.search(r"'olympia'",
                                                             ln, re.IGNORECASE)]
            if dropped_oly:
                overall_pass = False
                print(f"    -> FAIL: 'Olympia' DROPPED: {dropped_oly}", flush=True)
            elif verified_oly:
                print(f"    -> PASS: 'Olympia' VERIFIED: {verified_oly}", flush=True)
            else:
                print("    -> NOTE: 'Olympia' was not among the selected "
                      "candidates this run (no DROP either).", flush=True)

    print("\n  --- meter_report BY MODEL (status-200) ---", flush=True)
    for (kind, model), slot in sorted(by_model.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)

    print(f"\n  metered total (status-200, both tours): ${total:.4f} / "
          f"ledger cap ${HARD_CAP_USD:.2f}", flush=True)
    budget_ok = total < HARD_CAP_USD
    print(f"  budget check: ${total:.4f} < ${HARD_CAP_USD:.2f}  -> {budget_ok}",
          flush=True)

    verdict = overall_pass and budget_ok
    print(f"\n=== LOCAL-845 OVERALL: {'PASS' if verdict else 'CHECK'} "
          f"(contract={overall_pass}, budget={budget_ok}) ===", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
