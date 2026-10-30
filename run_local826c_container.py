"""run_local826c_container.py — LOCAL-826C live acceptance (ISOLATED container).

Proves the LOCAL-826C fix on the REAL cached path: the Rijksmuseum tour whose
"Merry Drinker" stop shipped a long bilingual title that was word-truncated into
a fragment and promoted as "This stop" (tour 866) now delivers 5 well-formed
stops — unique, sequential, every stop with a real narration body, NO stop
titled "This stop"/"Next stop", and NO stop whose body is a title fragment.

ONE TOUR, cheap museum arm, DISABLE_STOP_POOL=1:
    * "Rijks Museum, Amsterdam, Netherlands"   (5 stops)

PASS = 5 well-formed stops (check_stop_delivery returns []). If the Merry Drinker
work is not selected on this run, the fragment/placeholder path is already proven
by tests/test_local826c_long_title.py against the exact tour866_v2 evidence.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-826C TASK_BUDGET_USD=0.50. LiveRunMeter
records the run to the task ledger; a reserve gate refuses to START once the
ledger spend is at/over the cap.

METER CONTRACT (LOCAL-819/820): the container bind-mounts the shared meterlog
dir, writes the canonical PAID_API_LOG, installs the meter via
PYTHONPATH=/opt/meter and tags rows METER_SERVICE=LOCAL-826C.

DB: the isolated throwaway postgres only, seeded by the wrapper; never the
shared/live DB.
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

HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50")
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

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

TOURS = [
    ("Rijks Museum, Amsterdam, Netherlands", "museum", 5),
]

_D1V2_RE = re.compile(r"\[D1v2\]\s+(VERIFIED|DROPPED)\b.*")
_F3_RE = re.compile(r"\[F3\].*")
_DELIVERY_RE = re.compile(r"\[LOCAL-826[BC]\].*")
_T791B_RE = re.compile(r"\[LOCAL-791B\]\s+title\b.*")
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_MERRY = re.compile(r"(?i)merry drinker|berkemeyer|vrolijke drinker")


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


def main():
    print("=" * 70, flush=True)
    print("=== LOCAL-826C live run — Rijks long-title / 'This stop' fix "
          "(cheap arm, DISABLE_STOP_POOL=1) ===", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}   meter log: {METER_LOG}", flush=True)

    try:
        from venue_resolver import CORPUS_VERSION, cache_get, venue_works_cache_get
        print(f"  CORPUS_VERSION={CORPUS_VERSION}", flush=True)
        for qid, lang in (("Q190804", "nl"), ("Q190804", "en")):
            wc = venue_works_cache_get(qid, lang)
            print(f"  seeded venue_works_cache {qid}/{lang}: "
                  f"{len(wc) if wc else 0} works", flush=True)
        ch = cache_get("Q190804")
        print(f"  venue_corpus cache_get(Q190804) at v{CORPUS_VERSION}: "
              f"{'HIT' if ch else 'MISS (stale → rebuild)'}", flush=True)
    except Exception as e:
        print(f"  [LOCAL-826C] seed check failed ({e})", flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-826C] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g
    from tour_conclusion import check_stop_delivery
    import traceback as _tb

    results = []
    n_before_all = len(_meter_rows())

    for (location, tour_type, n_stops) in TOURS:
        meter = LiveRunMeter("LOCAL-826C")
        try:
            spent = meter.total_usd()
        except Exception:
            spent = 0.0
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        print(f"  ledger spent so far: ${spent:.3f} / ${HARD_CAP_USD:.2f}", flush=True)
        if spent >= HARD_CAP_USD:
            print(f"  [LOCAL-826C] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
                  f"— NOT running this tour", flush=True)
            try:
                meter.uninstall()
            except Exception:
                pass
            break

        t0 = time.time()
        d1v2_lines, delivery_lines, f3_lines, t791b_lines, titles = [], [], [], [], []
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
        try:
            with contextlib.redirect_stdout(_tee):
                text, _out, _coords = g.generate_tour_text(
                    location, tour_type, None, n_stops)
            dt = time.time() - t0
            captured = buf.getvalue()
            d1v2_lines = [m.group(0).strip() for m in _D1V2_RE.finditer(captured)]
            delivery_lines = [m.group(0).strip()
                              for m in _DELIVERY_RE.finditer(captured)]
            f3_lines = [m.group(0).strip() for m in _F3_RE.finditer(captured)]
            t791b_lines = [m.group(0).strip() for m in _T791B_RE.finditer(captured)]
            if text:
                titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]
                print(f"  generated in {dt:.0f}s — {len(titles)} stops", flush=True)
            else:
                print(f"  [LOCAL-826C] NO text in {dt:.0f}s", flush=True)
        except Exception as e:
            print(f"  [LOCAL-826C] raised: {e}", flush=True)
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

        viol = check_stop_delivery(text or "")
        merry_selected = bool(text and _MERRY.search(text))
        results.append({
            "location": location,
            "n_stops": len(titles),
            "titles": titles,
            "d1v2": d1v2_lines,
            "f3_log": f3_lines,
            "t791b_log": t791b_lines,
            "delivery_log": delivery_lines,
            "delivery_violations": viol,
            "merry_selected": merry_selected,
            "text": text or "",
        })

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70, flush=True)
    print("=== LOCAL-826C SUMMARY ===", flush=True)
    all_pass = True
    for r in results:
        well_formed = (r["n_stops"] == 5 and not r["delivery_violations"])
        all_pass = all_pass and well_formed
        print(f"\n  {r['location']}: {r['n_stops']} stops delivered "
              f"(Merry Drinker selected: {r['merry_selected']})", flush=True)
        print("    --- [LOCAL-791B] title composition ---", flush=True)
        for ln in r["t791b_log"] or ["(none captured)"]:
            print(f"      {ln[:140]}", flush=True)
        print("    --- [F3] title guard ---", flush=True)
        for ln in r["f3_log"] or ["(none fired)"]:
            print(f"      {ln[:140]}", flush=True)
        print("    --- delivered Stop headers ---", flush=True)
        for i, t in enumerate(r["titles"]):
            print(f"      Stop {i+1}: {t[:90]}", flush=True)
        print("    --- [LOCAL-826B/C] delivery-check log ---", flush=True)
        for ln in r["delivery_log"] or ["(none)"]:
            print(f"      {ln}", flush=True)
        verdict = ("PASS — 5 well-formed stops"
                   if well_formed else
                   f"FAIL — {r['n_stops']} stops, violations={r['delivery_violations']}")
        print(f"    --- VERDICT: {verdict}", flush=True)

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
    print(f"\n=== LOCAL-826C OVERALL: {'PASS' if all_pass else 'FAIL'} ===", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
