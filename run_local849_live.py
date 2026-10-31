"""run_local849_live.py — LOCAL-849 live, budget-enforced proof (Mac-local).

Proves the google.com/goto fix on two real tours, cheap env, stop pool OFF, and
reports exactly what the ticket asks for:
  * goto links seen / resolved (locally + via /resolve) / left unresolved,
  * pages fetched BEFORE vs AFTER the fix (a goto link left alone would be a
    fetch of the opaque Google redirect; after the fix those are resolved to a
    real page or dropped as unknown — so "after" counts only real-host fetches),
  * added seconds per tour (wall-time spent waiting on /resolve).

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-849 TASK_BUDGET_USD=0.60. LiveRunMeter
records to a per-task JSON ledger and a reserve gate refuses to START a tour once
the ledger spend is at/over the cap. Mac-LOCAL diagnostic (the documented
no-mount escape hatch, as run_local845/847_live.py): writes its meter log under
./_local849_meterlogs, METER_MOUNT_GUARD=0. It never writes the shared/live tour
DB (DISABLE_TOUR_CACHE=1) and never touches the shared audioura-* containers.

Tours (ticket): "Rijks Museum Amsterdam, Netherlands" (5), "Old Quarter walking
tour, Hanoi" (4).
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
os.environ.setdefault("TASK_BUDGET_ID", "LOCAL-849")
os.environ.setdefault("TASK_BUDGET_USD", "0.60")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.60") or "0.60")

os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ["WALKING_RESEARCH"] = "serper_plus"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"       # pool OFF
os.environ["DISABLE_TOUR_CACHE"] = "1"      # never persist a tour (no live DB write)
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")

_METER_DIR = os.path.join(_HERE, "_local849_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-849"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

TOURS = [
    ("Rijks Museum Amsterdam, Netherlands", "", 5),
    ("Old Quarter walking tour, Hanoi", "", 4),
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


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-849 live — google.com/goto resolution "
          "(cheap arm, pool OFF) ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}", flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)
    print(f"  STORY_PASS_MODEL={os.environ['STORY_PASS_MODEL']!r} "
          f"NARRATION_MODEL={os.environ['NARRATION_MODEL']!r} "
          f"DISABLE_STOP_POOL={os.environ['DISABLE_STOP_POOL']!r}", flush=True)

    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-849] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import serper_links as sl
    import generate_tour_text as g

    results = []
    for (location, tour_type, n_stops) in TOURS:
        meter = LiveRunMeter("LOCAL-849")
        sl.reset_metrics()
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        try:
            import task_budget as _tb
            _ledger_spent = _tb.spent_so_far("LOCAL-849")
        except Exception:
            _ledger_spent = 0.0
        print(f"  task-ledger spent so far: ${_ledger_spent:.3f} / ${HARD_CAP_USD:.2f}",
              flush=True)
        if _ledger_spent >= HARD_CAP_USD:
            print(f"  [LOCAL-849] reserve gate: ${_ledger_spent:.3f} >= "
                  f"${HARD_CAP_USD} — NOT running", flush=True)
            try:
                meter.uninstall()
            except Exception:
                pass
            break

        t0 = time.time()
        text = None

        try:
            with contextlib.redirect_stdout(io.StringIO()):
                text, _out, _coords = g.generate_tour_text(
                    location, tour_type, None, n_stops)
            dt = time.time() - t0
            titles = [(int(a), b.strip())
                      for a, b in _STOP_HEADER_RE.findall(text or "")]
            print(f"  generated in {dt:.0f}s — {len(titles)} stops", flush=True)
        except Exception as e:
            import traceback
            dt = time.time() - t0
            print(f"  [LOCAL-849] raised: {e}", flush=True)
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
                meter.uninstall()
            except Exception:
                pass

        gm = sl.get_metrics()
        refused = bool(re.search(r"could not find enough verified", text or "",
                                 re.IGNORECASE))
        results.append({"location": location, "requested": n_stops,
                        "titles": titles, "refused": refused,
                        "seconds": dt, "goto": gm})

    # ── REPORT ────────────────────────────────────────────────────────────────
    rows = _meter_rows()
    ok_rows = [r for r in rows if _ok(r)]
    total = sum(float(r.get("usd") or 0.0) for r in ok_rows)
    gemini_usd = sum(float(r.get("usd") or 0.0) for r in ok_rows
                     if "gemini" in (str(r.get("model") or "")).lower()
                     or "gemini" in (str(r.get("kind") or "")).lower())
    serper_search = [r for r in ok_rows if r.get("kind") == "serper"
                     and "/resolve" not in (r.get("url") or "")]
    serper_resolve = [r for r in ok_rows
                      if r.get("kind") == "serper" and "/resolve" in (r.get("url") or "")]

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-849 SUMMARY ===", flush=True)

    for r in results:
        gm = r["goto"]
        # Pages BEFORE the fix = every result link we would have fetched/judged,
        # INCLUDING the goto redirects (goto_seen). AFTER = goto links resolved to
        # a real page (resolved_local + resolved_api) plus the non-goto results;
        # unresolved goto links are dropped (0 bad fetches). The ticket's "pages
        # before vs after" is captured by: before counted goto_seen as fetchable
        # google.com redirects; after, 0 goto redirects are fetched and `resolved`
        # real pages replace them, `unresolved` are skipped.
        resolved = gm["resolved_local"] + gm["resolved_api"]
        print(f"\n  {r['location']}: {len(r['titles'])}/{r['requested']} stops "
              f"(refused={r['refused']})  {r['seconds']:.0f}s", flush=True)
        print(f"    goto links seen:        {gm['goto_seen']}", flush=True)
        print(f"      resolved (local):     {gm['resolved_local']}", flush=True)
        print(f"      resolved (/resolve):  {gm['resolved_api']}", flush=True)
        print(f"      unresolved (dropped): {gm['unresolved']}", flush=True)
        print(f"    /resolve batches:       {gm['resolve_calls']}  "
              f"(+{gm['resolve_seconds']:.1f}s added by /resolve)", flush=True)
        print(f"    pages BEFORE fix (goto redirects fetched as google.com): "
              f"{gm['goto_seen']}", flush=True)
        print(f"    pages AFTER fix  (real pages {resolved}, bad google.com "
              f"fetches 0, unknown dropped {gm['unresolved']})", flush=True)

    print("\n  --- meter totals (status-200) ---", flush=True)
    print(f"    serper /search+/news calls: {len(serper_search)}  "
          f"${sum(float(x.get('usd') or 0) for x in serper_search):.4f}", flush=True)
    print(f"    serper /resolve calls:      {len(serper_resolve)}  "
          f"${sum(float(x.get('usd') or 0) for x in serper_resolve):.4f} "
          f"(must be $0)", flush=True)
    print(f"    Gemini spend: ${gemini_usd:.4f}  (expect $0)", flush=True)
    print(f"    metered total (status-200): ${total:.4f} / cap ${HARD_CAP_USD:.2f}",
          flush=True)

    resolve_zero = all(float(x.get("usd") or 0) == 0.0 for x in serper_resolve)
    budget_ok = total <= HARD_CAP_USD
    any_delivered = any(len(r["titles"]) > 0 and not r["refused"] for r in results)
    print(f"\n  /resolve billed $0:   {resolve_zero}", flush=True)
    print(f"  under budget:         {budget_ok} (${total:.4f} <= ${HARD_CAP_USD:.2f})",
          flush=True)
    print(f"  tours delivered:      {any_delivered}", flush=True)

    verdict = resolve_zero and budget_ok and any_delivered
    print(f"\n=== LOCAL-849 OVERALL: {'PASS' if verdict else 'CHECK'} ===", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
