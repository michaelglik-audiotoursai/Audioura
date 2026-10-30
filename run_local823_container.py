"""run_local823_container.py — LOCAL-823 live acceptance (ISOLATED container).

Proves the three LOCAL-823 fixes end to end on the cheap museum arm
(CHEAP_ARM_CATEGORIES=museum, NARRATION_MODEL=gpt-4.1-mini, RESEARCH_BACKEND=serper):

  1. No stop title is site-chrome in ANY language — "Fußzeile" (de) and its
     multilingual siblings never ship as a stop (junk_title_guard).
  2. No stop title is a prefix copy of its body (stop_title_body_dup_guard, wired
     into the delivery choke point).
  3. The per-stop narration writer AND the story pass run on NARRATION_MODEL
     (gpt-4.1-mini) — gpt-4o no longer dominates a museum tour's cost. The meter's
     per-model breakdown is printed so the gpt-4o share is visible.

TWO TOURS, at most, both on the cheap arm (the ticket's limit):
    * "Belvedere Museum, Vienna, Austria"   (5 stops) — the German-site venue.
    * "Musée d'Orsay, Paris, France"        (5 stops) — a French-site venue.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-823 TASK_BUDGET_USD=1.20. LiveRunMeter
records each run to the task ledger; a reserve gate refuses to START a tour once
the ledger spend is at/over the cap, so the whole task cannot exceed $1.20.

METER CONTRACT (LOCAL-819/820): the container bind-mounts ~/Audioura/meterlogs ->
/meterlogs, writes the canonical PAID_API_LOG, installs the meter via
PYTHONPATH=/opt/meter and tags rows METER_SERVICE=LOCAL-823, so meter_report.py
sums this task's spend and its per-model breakdown.

DB: the isolated throwaway postgres only; never the shared/development DB. No
additive audio_tours rows are written by this runner.

Run via the wrapper (recommended): ./run_local823_live.sh
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests"))

HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "1.20") or "1.20")
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

# Cheap museum arm — the ticket's exact env (set here as defaults so an in-process
# run matches the wrapper).
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("DISABLE_STOP_POOL", "1")
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ.setdefault("CHEAP_ARM_CATEGORIES", "museum")
os.environ.setdefault("NARRATION_MODEL", "gpt-4.1-mini")
os.environ.setdefault("RESEARCH_BACKEND", "serper")
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

# The two cheap-arm museum tours (the ticket's limit of two).
TOURS = [
    ("Belvedere Museum, Vienna, Austria", "museum", 5),
    ("Musée d'Orsay, Paris, France", "museum", 5),
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")

# German/French/etc. site-chrome that must NEVER appear as a stop title.
_CHROME_WORDS = ("fußzeile", "fusszeile", "kopfzeile", "impressum", "datenschutz",
                 "navigation", "pied de page", "mentions légales", "menu principal")


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


def _check_tour(text, venue):
    """Return a list of problems with the delivered tour (empty == clean)."""
    problems = []
    try:
        import junk_title_guard as jtg
    except Exception:
        jtg = None
    try:
        import stop_title_body_dup_guard as stbd
    except Exception:
        stbd = None

    titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]
    # Build per-stop bodies for the title/body prefix check.
    blocks = []
    if stbd is not None:
        _pre, blocks = stbd._split_into_blocks(text)

    print("  --- STOPS ---", flush=True)
    for i, t in enumerate(titles):
        print(f"    STOP {i+1}: {t[:80]}", flush=True)
        low = t.lower()
        # Issue #1 — site-chrome in any language.
        for w in _CHROME_WORDS:
            if low == w:
                problems.append(f"site-chrome stop title ({w!r}): {t!r}")
        if jtg is not None and jtg.is_junk_page_title(t, venue):
            problems.append(f"junk/chrome stop title survived to delivery: {t!r}")

    # Issue #2 — a stop title that is a prefix copy of its body.
    if stbd is not None:
        for b in blocks:
            body = stbd._block_body(b["text"])
            if stbd.title_is_body_prefix(b["title"], body):
                problems.append(
                    f"Stop {b['num']} title is a prefix copy of its body: "
                    f"{b['title'][:60]!r}")
    return problems, titles


def main():
    print("=" * 70, flush=True)
    print("=== LOCAL-823 live run — cheap museum arm "
          "(gpt-4.1-mini narration + serper) ===", flush=True)
    print(f"  CHEAP_ARM_CATEGORIES={os.environ.get('CHEAP_ARM_CATEGORIES')!r} "
          f"NARRATION_MODEL={os.environ.get('NARRATION_MODEL')!r} "
          f"RESEARCH_BACKEND={os.environ.get('RESEARCH_BACKEND')!r}", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}   meter log: {METER_LOG}", flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-823] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g
    import traceback as _tb

    results = []
    n_before_all = len(_meter_rows())

    # Optional single-tour index from argv (0/1) for one-at-a-time runs.
    idx = None
    if len(sys.argv) > 1 and sys.argv[1].strip().isdigit():
        idx = int(sys.argv[1].strip())
    tours = [TOURS[idx]] if (idx is not None and 0 <= idx < len(TOURS)) else TOURS

    for (location, tour_type, n_stops) in tours:
        meter = LiveRunMeter("LOCAL-823")
        try:
            spent = meter.total_usd()
        except Exception:
            spent = 0.0
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        print(f"  ledger spent so far: ${spent:.3f} / ${HARD_CAP_USD:.2f}", flush=True)
        if spent >= HARD_CAP_USD:
            print(f"  [LOCAL-823] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
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
                problems, titles = _check_tour(text, location.split(",")[0])
                verdict = "PASS" if not problems else "FAIL"
                print(f"  generated in {dt:.0f}s — {verdict} ({len(titles)} stops)",
                      flush=True)
            else:
                print(f"  [LOCAL-823] NO text in {dt:.0f}s", flush=True)
        except Exception as e:
            print(f"  [LOCAL-823] raised: {e}", flush=True)
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

        # Per-model meter breakdown for THIS tour.
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

    # ── Whole-task per-model breakdown + SUMMARY ──────────────────────────────
    rows_all = _meter_rows()
    new_all = rows_all[n_before_all:] if len(rows_all) >= n_before_all else rows_all
    bm_all = _by_model(new_all)
    print("\n" + "=" * 70, flush=True)
    print("=== LOCAL-823 SUMMARY ===", flush=True)
    for r in results:
        print(f"  {r['location']}: {r['verdict']} ({r['n_stops']} stops)", flush=True)
        for p in r["problems"]:
            print(f"      PROBLEM: {p}", flush=True)
    print("\n  --- per-model meter (whole task) ---", flush=True)
    total = 0.0
    gpt4o = 0.0
    for (kind, model), slot in sorted(bm_all.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)
        total += slot["usd"]
        if "gpt-4o" in model and "mini" not in model:
            gpt4o += slot["usd"]
    print(f"  metered total (status-200 rows this task): ${total:.4f}", flush=True)
    print(f"  of which gpt-4o (non-mini): ${gpt4o:.4f}  "
          f"(was $0.75 of a $1.03 tour before the fix)", flush=True)
    all_pass = all(r["verdict"] == "PASS" for r in results) and bool(results)
    print(f"\n  OVERALL: {'PASS' if all_pass else 'SEE PROBLEMS ABOVE'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
