"""run_local828_container.py — LOCAL-828 live acceptance (ISOLATED container).

Proves the venue-identity gate end to end on the cheap museum arm
(CHEAP_ARM_CATEGORIES=museum, NARRATION_MODEL=gpt-4.1-mini, RESEARCH_BACKEND=serper):

  * Stop 1 (and every stop) of a MUSEUM tour is about the REQUESTED venue — no
    paragraph about ANOTHER museum in another city (the Rijksmuseum Stop-1 "Museum
    Catharijneconvent, Utrecht" bleed). The runner scans the delivered text for a
    foreign-museum subject / a contradicting city and FAILS the tour if any
    survives; it also reports every ``[LOCAL-828] other-venue passage dropped`` the
    gate logged (the gate firing is the fix working).

TWO TOURS, at most, both on the cheap arm (the ticket's limit):
    * "Rijksmuseum, Amsterdam, Netherlands"      (5 stops) — the reported bug.
    * "The Met Fifth Avenue, New York"           (5 stops) — shared-name sibling
      (must not pull in The Met Cloisters).

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-828 TASK_BUDGET_USD=0.80. LiveRunMeter
records each run to the task ledger; a reserve gate refuses to START a tour once
the ledger spend is at/over the cap, so the whole task cannot exceed $0.80.

METER CONTRACT (LOCAL-819/820): the container bind-mounts the shared meterlog dir
-> /meterlogs, writes the canonical PAID_API_LOG, installs the meter via
PYTHONPATH=/opt/meter and tags rows METER_SERVICE=LOCAL-828, so meter_report.py
sums this task's spend and its per-model breakdown.

DB: the isolated throwaway postgres only; never the shared/development DB.

Run via the wrapper (recommended): ./run_local828_live.sh
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests"))

HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.80") or "0.80")
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

# Cheap museum arm — the ticket's exact env (defaults so an in-process run matches
# the wrapper).
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("DISABLE_STOP_POOL", "1")
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ.setdefault("CHEAP_ARM_CATEGORIES", "museum")
os.environ.setdefault("NARRATION_MODEL", "gpt-4.1-mini")
os.environ.setdefault("SERPER_RESEARCH_MODEL", "gpt-4.1-mini")
os.environ.setdefault("RESEARCH_BACKEND", "serper")
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

# The two cheap-arm museum tours (the ticket's limit of two).
TOURS = [
    ("Rijksmuseum, Amsterdam, Netherlands", "museum", 5),
    ("The Met Fifth Avenue, New York", "museum", 5),
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")

# Other-venue subjects that must NOT survive in each tour's delivered text. These
# are the known sibling/foreign venues for the two requested venues; if any name
# appears in the delivered narration the gate failed to catch its passage.
_FORBIDDEN_BY_VENUE = {
    "Rijksmuseum": ["Catharijneconvent", "Utrecht", "Van Gogh Museum",
                    "Stedelijk", "Mauritshuis"],
    "The Met Fifth Avenue": ["Met Cloisters", "The Cloisters", "Fort Tryon"],
}


def _meter_rows():
    rows = []
    try:
        with open(METER_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return rows


def _by_model(rows):
    """{(kind, model): {'calls', 'usd'}} for status-200 rows."""
    out = {}
    for r in rows:
        if r.get("status") not in (200, "200"):
            continue
        key = (r.get("kind") or "?", r.get("model") or "?")
        slot = out.setdefault(key, {"calls": 0, "usd": 0.0})
        slot["calls"] += 1
        try:
            slot["usd"] += float(r.get("usd") or 0.0)
        except (TypeError, ValueError):
            pass
    return out


def _check_tour(text, venue_request):
    """Return (problems, titles). A problem is a forbidden other-venue subject
    surviving in the delivered text."""
    problems = []
    titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]
    print("  --- STOPS ---", flush=True)
    for i, t in enumerate(titles):
        print(f"    STOP {i+1}: {t[:80]}", flush=True)

    venue_head = venue_request.split(",")[0].strip()
    low = text.lower()
    for forbidden in _FORBIDDEN_BY_VENUE.get(venue_head, []):
        if forbidden.lower() in low:
            # Report WHERE it survived (first ~120 chars of context) so a reviewer
            # can confirm it is an other-venue bleed, not an incidental mention.
            idx = low.find(forbidden.lower())
            ctx = text[max(0, idx - 60):idx + 60].replace("\n", " ")
            problems.append(f"other-venue term {forbidden!r} survived in delivered "
                            f"text: …{ctx}…")
    return problems, titles


def main():
    print("=" * 70, flush=True)
    print("=== LOCAL-828 live run — venue-identity gate, cheap museum arm "
          "(gpt-4.1-mini + serper) ===", flush=True)
    print(f"  CHEAP_ARM_CATEGORIES={os.environ.get('CHEAP_ARM_CATEGORIES')!r} "
          f"NARRATION_MODEL={os.environ.get('NARRATION_MODEL')!r} "
          f"RESEARCH_BACKEND={os.environ.get('RESEARCH_BACKEND')!r}", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}   meter log: {METER_LOG}", flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-828] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g
    import traceback as _tb

    results = []
    n_before_all = len(_meter_rows())

    idx = None
    if len(sys.argv) > 1 and sys.argv[1].strip().isdigit():
        idx = int(sys.argv[1].strip())
    tours = [TOURS[idx]] if (idx is not None and 0 <= idx < len(TOURS)) else TOURS

    for (location, tour_type, n_stops) in tours:
        meter = LiveRunMeter("LOCAL-828")
        try:
            spent = meter.total_usd()
        except Exception:
            spent = 0.0
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        print(f"  ledger spent so far: ${spent:.3f} / ${HARD_CAP_USD:.2f}", flush=True)
        if spent >= HARD_CAP_USD:
            print(f"  [LOCAL-828] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
                  f"— NOT running this tour", flush=True)
            try:
                meter.uninstall()
            except Exception:
                pass
            break

        n_before = len(_meter_rows())
        t0 = time.time()
        verdict, problems, titles = "NO_TEXT", [], []
        try:
            text, _out, _coords = g.generate_tour_text(location, tour_type, None, n_stops)
            dt = time.time() - t0
            if text:
                problems, titles = _check_tour(text, location)
                verdict = "PASS" if not problems else "FAIL"
                print(f"  generated in {dt:.0f}s — {verdict} ({len(titles)} stops)",
                      flush=True)
            else:
                print(f"  [LOCAL-828] NO text in {dt:.0f}s", flush=True)
        except Exception as e:
            print(f"  [LOCAL-828] raised: {e}", flush=True)
            _tb.print_exc()
        finally:
            try:
                meter.add_generation(g)
            except Exception:
                pass
            try:
                meter.record()
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

        rows_after = _meter_rows()
        new_rows = rows_after[n_before:] if len(rows_after) >= n_before else rows_after
        bm = _by_model(new_rows)
        print("  --- per-model meter (this tour) ---", flush=True)
        for (kind, model), slot in sorted(bm.items(), key=lambda kv: -kv[1]["usd"]):
            print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
                  flush=True)
        results.append({
            "location": location, "verdict": verdict,
            "n_stops": len(titles), "problems": problems,
            "by_model": {f"{k[0]}/{k[1]}": v for k, v in bm.items()},
        })

    rows_all = _meter_rows()
    new_all = rows_all[n_before_all:] if len(rows_all) >= n_before_all else rows_all
    bm_all = _by_model(new_all)
    print("\n" + "=" * 70, flush=True)
    print("=== LOCAL-828 SUMMARY ===", flush=True)
    for r in results:
        print(f"  {r['location']}: {r['verdict']} ({r['n_stops']} stops)", flush=True)
        for p in r["problems"]:
            print(f"      PROBLEM: {p}", flush=True)
    print("\n  --- per-model meter (whole task) ---", flush=True)
    total = 0.0
    for (kind, model), slot in sorted(bm_all.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)
        total += slot["usd"]
    print(f"  metered total (status-200 rows this task): ${total:.4f}", flush=True)
    all_pass = all(r["verdict"] == "PASS" for r in results) and bool(results)
    print(f"\n  OVERALL: {'PASS' if all_pass else 'SEE PROBLEMS ABOVE'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
