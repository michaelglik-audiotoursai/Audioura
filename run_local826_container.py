"""run_local826_container.py — LOCAL-826 live acceptance (ISOLATED container).

Exercises the museum canonical-title verification end to end on the cheap museum
arm (CHEAP_ARM_CATEGORIES=museum, NARRATION_MODEL=gpt-4.1-mini,
RESEARCH_BACKEND=serper), DISABLE_STOP_POOL=1, and reports the D1v2
VERIFIED/DROPPED lines the ticket asks for:

  Bug 1 — famous works present in the venue's SPARQL set must VERIFY from a
          candidate in EITHER language (Orsay: L'Origine du monde, Olympia,
          La Nuit étoilée, La Naissance de Vénus).
  Bug 2 — a wrong work must NEVER be VERIFIED on a shared place name
          (L'Église d'Auvers-sur-Oise ≠ Chaumes de Cordeville à Auvers-sur-Oise).
  Bug 3 — a shortfall caused by our own filters must NOT say "N exhibitions on
          view"; it uses the neutral honest line.

TWO TOURS, at most, both on the cheap arm (the ticket's limit):
    * "Orsay Museum, Paris, France"            (5 stops)
    * "Belvedere Palace, Vienna, Austria"      (5 stops)

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-826 TASK_BUDGET_USD=0.90. LiveRunMeter
records each run to the task ledger; a reserve gate refuses to START a tour once
the ledger spend is at/over the cap, so the whole task cannot exceed $0.90.

METER CONTRACT (LOCAL-819/820): the container bind-mounts ~/Audioura/meterlogs ->
/meterlogs, writes the canonical PAID_API_LOG, installs the meter via
PYTHONPATH=/opt/meter and tags rows METER_SERVICE=LOCAL-826.

DB: the isolated throwaway postgres only; never the shared/development DB.

Run via the wrapper (recommended): ./run_local826_live.sh
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

HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.90") or "0.90")
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
    ("Orsay Museum, Paris, France", "museum", 5),
    ("Belvedere Palace, Vienna, Austria", "museum", 5),
]

_D1V2_RE = re.compile(r"\[D1v2\]\s+(VERIFIED|DROPPED)\b.*")
_SHORTFALL_RE = re.compile(
    r"(currently has \d+ exhibition|exhibitions on view|"
    r"We could confirm \d+ stop|rather than the \d+ you asked for)", re.I)
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")


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
    print("=== LOCAL-826 live run — museum canonical verification "
          "(cheap arm, DISABLE_STOP_POOL=1) ===", flush=True)
    print(f"  CHEAP_ARM_CATEGORIES={os.environ.get('CHEAP_ARM_CATEGORIES')!r} "
          f"NARRATION_MODEL={os.environ.get('NARRATION_MODEL')!r} "
          f"RESEARCH_BACKEND={os.environ.get('RESEARCH_BACKEND')!r} "
          f"DISABLE_STOP_POOL={os.environ.get('DISABLE_STOP_POOL')!r}", flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}   meter log: {METER_LOG}", flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-826] live_run_meter unavailable ({e}); aborting", flush=True)
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
        meter = LiveRunMeter("LOCAL-826")
        try:
            spent = meter.total_usd()
        except Exception:
            spent = 0.0
        print(f"\n--- {location} ({n_stops} stops) ---", flush=True)
        print(f"  ledger spent so far: ${spent:.3f} / ${HARD_CAP_USD:.2f}", flush=True)
        if spent >= HARD_CAP_USD:
            print(f"  [LOCAL-826] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
                  f"— NOT running this tour", flush=True)
            try:
                meter.uninstall()
            except Exception:
                pass
            break

        n_before = len(_meter_rows())
        t0 = time.time()
        d1v2_lines, shortfall_lines, titles = [], [], []
        text = None
        # Capture the generator's stdout so we can extract the D1v2 lines while
        # STILL echoing everything (the live log keeps the full trace).
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
            d1v2_lines = [m.group(0).strip()
                          for m in _D1V2_RE.finditer(captured)]
            if text:
                titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]
                shortfall_lines = [ln.strip() for ln in text.splitlines()
                                   if _SHORTFALL_RE.search(ln)]
                print(f"  generated in {dt:.0f}s — {len(titles)} stops", flush=True)
            else:
                print(f"  [LOCAL-826] NO text in {dt:.0f}s", flush=True)
        except Exception as e:
            print(f"  [LOCAL-826] raised: {e}", flush=True)
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
        results.append({
            "location": location,
            "n_stops": len(titles),
            "titles": titles,
            "d1v2": d1v2_lines,
            "shortfall": shortfall_lines,
            "by_model": {f"{k[0]}/{k[1]}": v for k, v in bm.items()},
        })

    # ── SUMMARY: the D1v2 VERIFIED/DROPPED lines the ticket asks for ──────────
    print("\n" + "=" * 70, flush=True)
    print("=== LOCAL-826 SUMMARY — D1v2 VERIFIED/DROPPED lines ===", flush=True)
    for r in results:
        print(f"\n  {r['location']}: {r['n_stops']} stops delivered", flush=True)
        if r["d1v2"]:
            for ln in r["d1v2"]:
                print(f"      {ln}", flush=True)
        else:
            print("      (no [D1v2] lines captured)", flush=True)
        print("    --- delivered stop titles ---", flush=True)
        for i, t in enumerate(r["titles"]):
            print(f"      Stop {i+1}: {t[:90]}", flush=True)
        if r["shortfall"]:
            print("    --- shortfall / count sentence(s) ---", flush=True)
            for ln in r["shortfall"]:
                print(f"      {ln}", flush=True)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
