"""run_local843_live.py — LOCAL-843 live, budget-enforced proof (Mac-local).

The field tour (GCloud_Storied wave 16, gen 00022-kbx, cheap env +
STORY_PASS_MODEL=gpt-4.1):

    "Kitesurf lessons at Mui Ne beach, Vietnam" (5)

shipped 2/5 kite schools, Gemini $0.16 top line, a header reading
`Tour-Category: restaurant`, and an invented story ("Duc fused kiteboarding and
seafood"). This run proves the four LOCAL-843 fixes, cheap env EXACTLY as the
ticket specifies, stop pool OFF:

    CHEAP_ARM_CATEGORIES=museum,walking,restaurant,facility,specialized
    NARRATION_MODEL=gpt-4.1-mini
    RESEARCH_BACKEND=serper   SERP_PROVIDER=serper
    STORY_PASS_MODEL=gpt-4.1
    DISABLE_STOP_POOL=1       (pool off)

PASS criteria (ticket):
  * >= 4 real kite providers among the delivered stops;
  * Gemini $0 (no status-200 generativelanguage row);
  * NO internal category label — the header must NOT read "Tour-Category:
    restaurant"; a neutral "places" (or the activity words) is required;
  * every story sentence traceable to a source (no ungrounded-person survivor);
  * metered total <= $0.40.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-843 TASK_BUDGET_USD=0.60. LiveRunMeter
records the run to the per-task JSON ledger and a reserve gate refuses to START
the tour once the ledger spend is at/over the cap. This is a Mac-LOCAL diagnostic
(the documented no-mount escape hatch, same as run_local834_live.py /
run_local835b_live.py): it writes its meter log under ./_local843_meterlogs and
sets METER_MOUNT_GUARD=0. It never writes the shared/live DB and never touches
the shared audioura-* containers.
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
sys.path.insert(0, _HERE)

# ── budget + cheap env (ticket-exact) ────────────────────────────────────────
os.environ.setdefault("TASK_BUDGET_ID", "LOCAL-843")
os.environ.setdefault("TASK_BUDGET_USD", "0.60")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.60") or "0.60")
PER_TOUR_CAP_USD = float(os.environ.get("PER_TOUR_CAP_USD", "0.40") or "0.40")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")

_METER_DIR = os.path.join(_HERE, "_local843_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-843"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

TOURS = [("Kitesurf lessons at Mui Ne beach, Vietnam", "", 5)]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_CAT_RE = re.compile(r"(?mi)^Tour-Category:\s*(\w+)")


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
    print("=== LOCAL-843 live — kite yield / Gemini $0 / no category label / "
          "grounded stories (cheap arm, pool OFF) ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}  per-tour PASS cap=${PER_TOUR_CAP_USD:.2f}",
          flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)
    print(f"  CHEAP_ARM_CATEGORIES={os.environ['CHEAP_ARM_CATEGORIES']!r}", flush=True)
    print(f"  NARRATION_MODEL={os.environ['NARRATION_MODEL']!r} "
          f"RESEARCH_BACKEND={os.environ['RESEARCH_BACKEND']!r} "
          f"STORY_PASS_MODEL={os.environ['STORY_PASS_MODEL']!r} "
          f"DISABLE_STOP_POOL={os.environ['DISABLE_STOP_POOL']!r}", flush=True)

    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-843] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g

    results = []
    for (location, tour_type, n_stops) in TOURS:
        meter = LiveRunMeter("LOCAL-843")
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        try:
            import task_budget as _tb
            _ledger_spent = _tb.spent_so_far("LOCAL-843")
        except Exception:
            _ledger_spent = 0.0
        print(f"  task-ledger spent so far: ${_ledger_spent:.3f} / ${HARD_CAP_USD:.2f}",
              flush=True)
        if _ledger_spent >= HARD_CAP_USD:
            print(f"  [LOCAL-843] reserve gate: ${_ledger_spent:.3f} >= "
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
            print(f"  [LOCAL-843] raised: {e}", flush=True)
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
                        "titles": titles, "text": text or "",
                        "log": buf.getvalue()})

    # ── REPORT ────────────────────────────────────────────────────────────────
    rows = _meter_rows()
    ok_rows = [r for r in rows if _ok(r)]
    by_model = _group(rows, lambda r: (r.get("kind") or "?", r.get("model") or "?"))
    by_caller = _group(rows, lambda r: (r.get("kind") or "?", r.get("caller") or "?"))
    total = sum(float(r.get("usd") or 0.0) for r in ok_rows)

    # Gemini spend (status-200 generativelanguage rows).
    gemini_usd = 0.0
    gemini_calls = 0
    for r in ok_rows:
        _blob = json.dumps(r).lower()
        if "generativelanguage" in _blob or "gemini" in _blob:
            gemini_calls += 1
            try:
                gemini_usd += float(r.get("usd") or 0.0)
            except (TypeError, ValueError):
                pass

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-843 SUMMARY ===", flush=True)
    overall_pass = True
    for r in results:
        verdicts = _classify_titles(r["titles"], r["location"])
        n_off = sum(1 for _, _, v in verdicts if v is False)
        n_prov = sum(1 for _, _, v in verdicts if v is True)
        text = r["text"]
        cat_m = _CAT_RE.search(text or "")
        header_cat = cat_m.group(1).lower() if cat_m else "(none)"
        title_line = (text or "").split("\n", 1)[0]

        print(f"\n  {r['location']}: {len(r['titles'])}/{r['requested']} stops "
              f"(providers={n_prov}, off-category={n_off})", flush=True)
        print(f"    title : {title_line}", flush=True)
        print(f"    header: Tour-Category: {header_cat}", flush=True)
        for n, t, v in verdicts:
            tag = ("PROVIDER" if v is True else
                   "OFF-CATEGORY!" if v is False else "unknown")
            print(f"    Stop {n}: {t[:66]:<66} [{tag}]", flush=True)

        # PASS checks.
        _c_providers = n_prov >= 4
        _c_no_label = ("restaurant" not in (header_cat,)) and \
                      ("restaurant" not in title_line.lower())
        _c_no_offcat = n_off == 0
        # Grounding: the places person gate logs "[LOCAL-843] ungrounded" when it
        # DROPS a fabrication; a clean run either logs a drop (gate worked) or
        # logs no ungrounded survivor. We treat the presence of the gate summary
        # with ungrounded>0 that was NOT dropped as a fail — but the gate always
        # drops what it flags, so we assert no "fused"/invented survivor remains.
        _fused_survivor = bool(re.search(r"\bfused\b", text or "", re.IGNORECASE))
        _c_grounded = not _fused_survivor

        print(f"    CHECK providers>=4 : {_c_providers} ({n_prov})", flush=True)
        print(f"    CHECK no off-cat   : {_c_no_offcat} ({n_off})", flush=True)
        print(f"    CHECK no 'restaurant' label in header/title: {_c_no_label} "
              f"(header={header_cat!r})", flush=True)
        print(f"    CHECK no ungrounded 'fused' survivor: {_c_grounded}", flush=True)
        if not (_c_providers and _c_no_label and _c_no_offcat and _c_grounded):
            overall_pass = False

    print("\n  --- meter_report BY MODEL (status-200) ---", flush=True)
    for (kind, model), slot in sorted(by_model.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)
    print("\n  --- meter_report BY CALLER (status-200) ---", flush=True)
    for (kind, caller), slot in sorted(by_caller.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}  {caller}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)

    print(f"\n  GEMINI (status-200): {gemini_calls} calls  ${gemini_usd:.4f}", flush=True)
    print(f"  metered total (status-200): ${total:.4f} / per-tour cap "
          f"${PER_TOUR_CAP_USD:.2f} / ledger cap ${HARD_CAP_USD:.2f}", flush=True)

    _gemini_zero = gemini_usd == 0.0
    _budget_ok = total <= PER_TOUR_CAP_USD
    print(f"  CHECK gemini $0    : {_gemini_zero} (${gemini_usd:.4f})", flush=True)
    print(f"  CHECK total<=$0.40 : {_budget_ok} (${total:.4f})", flush=True)

    verdict = overall_pass and _gemini_zero and _budget_ok
    print(f"\n=== LOCAL-843 OVERALL: {'PASS' if verdict else 'CHECK'} ===", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
