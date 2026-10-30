"""run_local832b_container.py — LOCAL-832B live acceptance (ISOLATED container).

BOUNCE of LOCAL-832. The 832 refill cost ×2 and kept nothing on the cheap arm;
the real defect LEAD identified is that a story the pass WROTE (``[LOCAL-490]
ok=True``) did not survive into the delivered prose — the narration merge
dissolved its consecutive run, so story_opportunity_scan read the delivered text
as agency=0 stakes=0. 832B:

  1. STORY-SURVIVAL (story_survival.py, wired in generate_tour_text's main apply
     loop): when the pass story CLEARS Michael's bar but the delivered prose does
     NOT, the pass story is re-seated as its own leading block so it survives into
     delivery and the scan sees it. Deterministic, no extra LLM spend.
  2. REFILL made cheap/bounded (museum_story_refill.py): ONE round by default, each
     candidate research-pre-checked before a narration call is spent, whole refill
     aborts after two consecutive failures. Extra spend logged.

PASS (ticket): 5/5 delivered each tour, >= 3 of 5 stops clear the story bar per
tour, and cost per tour <= $0.40. The runner measures each delivered stop body
with story_opportunity_scan (the SAME judge the gate uses) and reports every
``[LOCAL-487] ... NO VALID STORY`` rejection, every ``[LOCAL-832B] story-survival``
line and every ``[LOCAL-832] story-gate refill`` line.

TWO TOURS, cheap museum arm, DISABLE_STOP_POOL=1:
    * "Orsay Museum, Paris, France"           (5 stops)
    * "Rijksmuseum, Amsterdam, Netherlands"   (5 stops)

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-832B TASK_BUDGET_USD=0.70 (whole-task cap,
LOCAL-827). LiveRunMeter records each run to the task ledger; a reserve gate
refuses to START a tour once the ledger spend is at/over the cap, so the whole
task cannot exceed $0.70.

DB: the isolated throwaway postgres only, seeded by the wrapper from the REAL
cached rows (Rijks Q190804 + Orsay Q23402); never the shared/live DB. Never an
audioura-* container.

Run via the wrapper (recommended): ./run_local832b_live.sh
"""
import io
import json
import os
import re
import sys
import time
import contextlib

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests"))

TASK_ID = os.environ.get("TASK_BUDGET_ID", "LOCAL-832B") or "LOCAL-832B"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.70") or "0.70")
PER_TOUR_PASS_USD = float(os.environ.get("PER_TOUR_PASS_USD", "0.40") or "0.40")
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

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

TOURS = [
    ("Orsay Museum, Paris, France", "museum", 5),
    ("Rijksmuseum, Amsterdam, Netherlands", "museum", 5),
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_NO_STORY_RE = re.compile(r"\[LOCAL-487\].*NO VALID STORY.*")
_SURVIVAL_RE = re.compile(r"\[LOCAL-832B\].*")
_REFILL_RE = re.compile(r"\[LOCAL-832\].*")


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


def _split_stop_bodies(text):
    if not text:
        return []
    matches = list(_STOP_HEADER_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        out.append((int(m.group(1)), m.group(2).strip(), body))
    return out


def _measure_stories(stop_bodies):
    try:
        from story_opportunity_scan import measure, verdict
    except Exception as e:
        return [{"error": f"scan unavailable: {e}"}], False
    per = []
    all_ok = True
    for (no, title, body) in stop_bodies:
        try:
            v = verdict(measure(body))
            has_story = not v.get("needs_additional_story", True)
        except Exception as e:
            has_story = False
            v = {"why": f"measure error: {e}"}
        per.append({"stop": no, "title": title, "has_story": has_story,
                    "why": (v.get("why") or "")[:120]})
        if not has_story:
            all_ok = False
    return per, all_ok


def main():
    print("=" * 70, flush=True)
    print("=== LOCAL-832B live run — story-survival + bounded refill "
          "(cheap arm, DISABLE_STOP_POOL=1) ===", flush=True)
    print(f"  TASK_BUDGET_ID={TASK_ID!r} HARD CAP=${HARD_CAP_USD:.2f} "
          f"per-tour PASS <= ${PER_TOUR_PASS_USD:.2f}   meter log: {METER_LOG}",
          flush=True)

    try:
        from venue_resolver import CORPUS_VERSION, venue_works_cache_get
        print(f"  CORPUS_VERSION={CORPUS_VERSION}", flush=True)
        for qid, lang in (("Q23402", "fr"), ("Q190804", "nl"), ("Q190804", "en")):
            wc = venue_works_cache_get(qid, lang)
            print(f"  seeded venue_works_cache {qid}/{lang}: "
                  f"{len(wc) if wc else 0} works", flush=True)
    except Exception as e:
        print(f"  [LOCAL-832B] seed check failed ({e})", flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-832B] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g
    from tour_conclusion import check_stop_delivery
    import traceback as _tb

    results = []
    n_before_all = len(_meter_rows())

    idx = None
    if len(sys.argv) > 1 and sys.argv[1].strip().isdigit():
        idx = int(sys.argv[1].strip())
    tours = [TOURS[idx]] if (idx is not None and 0 <= idx < len(TOURS)) else TOURS

    for (location, tour_type, n_stops) in tours:
        meter = LiveRunMeter(TASK_ID)
        try:
            spent = meter.total_usd()
        except Exception:
            spent = 0.0
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        print(f"  ledger spent so far: ${spent:.3f} / ${HARD_CAP_USD:.2f}", flush=True)
        if spent >= HARD_CAP_USD:
            print(f"  [LOCAL-832B] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
                  f"— NOT running this tour", flush=True)
            try:
                meter.uninstall()
            except Exception:
                pass
            break

        t0 = time.time()
        no_story_lines, survival_lines, refill_lines, bodies = [], [], [], []
        text = None
        buf = io.StringIO()

        class _Tee:
            def __init__(self, *streams):
                self._s = streams

            def write(self, data):
                for s in self._s:
                    s.write(data)
                return len(data)

            def flush(self):
                for s in self._s:
                    try:
                        s.flush()
                    except Exception:
                        pass

        _tee = _Tee(sys.stdout, buf)
        _tour_usd = 0.0
        _usd_before = 0.0
        try:
            _usd_before = meter.total_usd()
        except Exception:
            _usd_before = 0.0
        try:
            with contextlib.redirect_stdout(_tee):
                text, _out, _coords = g.generate_tour_text(
                    location, tour_type, None, n_stops)
            dt = time.time() - t0
            captured = buf.getvalue()
            no_story_lines = [m.group(0).strip()
                              for m in _NO_STORY_RE.finditer(captured)]
            survival_lines = [m.group(0).strip()
                              for m in _SURVIVAL_RE.finditer(captured)]
            # Refill lines are [LOCAL-832] but not [LOCAL-832B]; keep them distinct.
            refill_lines = [m.group(0).strip()
                            for m in _REFILL_RE.finditer(captured)
                            if "LOCAL-832B" not in m.group(0)]
            bodies = _split_stop_bodies(text or "")
            print(f"  generated in {dt:.0f}s — {len(bodies)} stops", flush=True)
        except Exception as e:
            print(f"  [LOCAL-832B] raised: {e}", flush=True)
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
                _tour_usd = meter.total_usd() - _usd_before
            except Exception:
                _tour_usd = 0.0
            try:
                print("  " + meter.summary().replace("\n", "\n  "), flush=True)
            except Exception:
                pass
            try:
                meter.uninstall()
            except Exception:
                pass

        per_stop, all_story_ok = _measure_stories(bodies)
        viol = check_stop_delivery(text or "")
        results.append({
            "location": location,
            "n_requested": n_stops,
            "n_stops": len(bodies),
            "per_stop": per_stop,
            "all_story_ok": all_story_ok,
            "no_story_lines": no_story_lines,
            "survival_lines": survival_lines,
            "refill_lines": refill_lines,
            "delivery_violations": viol,
            "tour_usd": _tour_usd,
        })

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70, flush=True)
    print("=== LOCAL-832B SUMMARY ===", flush=True)
    # PASS (ticket): 5/5 delivered + sequential + delivery-clean, >= 3/5 clear the
    # story bar, and cost per tour <= $0.40.
    overall_pass = True
    for r in results:
        stories_ok = sum(1 for s in r["per_stop"] if s.get("has_story"))
        nums = [s["stop"] for s in r["per_stop"] if "stop" in s]
        sequential = nums == list(range(1, r["n_requested"] + 1))
        count_ok = r["n_stops"] == r["n_requested"] and sequential
        delivery_ok = not r["delivery_violations"]
        story_ok = stories_ok >= 3
        cost_ok = r["tour_usd"] <= PER_TOUR_PASS_USD
        tour_pass = count_ok and delivery_ok and story_ok and cost_ok
        overall_pass = overall_pass and tour_pass
        print(f"\n  {r['location']}: {r['n_stops']}/{r['n_requested']} stops "
              f"delivered (sequential={sequential}, delivery_clean={delivery_ok}) "
              f"— {'PASS' if tour_pass else 'FAIL'}", flush=True)
        print(f"    story bar: {stories_ok}/{r['n_requested']} clear "
              f"(need >= 3) -> {'OK' if story_ok else 'FAIL'}", flush=True)
        print(f"    cost: ${r['tour_usd']:.4f} (need <= ${PER_TOUR_PASS_USD:.2f}) "
              f"-> {'OK' if cost_ok else 'FAIL'}", flush=True)
        print("    --- [LOCAL-487] story-gate rejections (gate firing = working) ---",
              flush=True)
        for ln in (r["no_story_lines"] or ["(none)"]):
            print(f"      {ln}", flush=True)
        print("    --- [LOCAL-832B] story-survival lines ---", flush=True)
        for ln in (r["survival_lines"] or ["(none)"]):
            print(f"      {ln}", flush=True)
        print("    --- [LOCAL-832] refill lines ---", flush=True)
        for ln in (r["refill_lines"] or ["(none)"]):
            print(f"      {ln}", flush=True)
        print("    --- per-stop story verdict on DELIVERED text ---", flush=True)
        for s in r["per_stop"]:
            if "error" in s:
                print(f"      {s['error']}", flush=True)
                continue
            print(f"      Stop {s['stop']} '{s['title'][:46]}': "
                  f"{'STORY' if s['has_story'] else 'NO STORY — ' + s['why']}",
                  flush=True)
        print(f"    --- delivery check: "
              f"{'CLEAN' if delivery_ok else r['delivery_violations']}", flush=True)

    rows_all = _meter_rows()
    new_all = rows_all[n_before_all:] if len(rows_all) >= n_before_all else rows_all
    bm_all = _by_model(new_all)
    print("\n  --- per-model meter (whole task, status-200) ---", flush=True)
    total = 0.0
    for (kind, model), slot in sorted(bm_all.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"    {kind}/{model}: {slot['calls']} calls  ${slot['usd']:.4f}",
              flush=True)
        total += slot["usd"]
    print(f"  metered total (status-200 rows this task): ${total:.4f} "
          f"/ cap ${HARD_CAP_USD:.2f}", flush=True)

    print(f"\n  OVERALL: {'PASS' if overall_pass else 'FAIL'}", flush=True)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
