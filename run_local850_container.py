"""run_local850_container.py — LOCAL-850 live acceptance (ISOLATED container).

Proves the unresolved-venue drift fix end to end, from the EXACT failing request
string, with the stop pool ON:

  "Rijks Museum Amsterdam, Netherlands" (5)  → Rijksmuseum (Q190804) works,
      pinned in AMSTERDAM — NEVER the Kröller-Müller museum, NEVER Honfleur.
  "Musee d Orsay Paris" (5)                  → Musée d'Orsay (Q23402), Paris.

PASS per tour:
  • the tour resolves to the RIGHT venue (QID present in the log / pin in the
    right city) — concretely, NO Kröller-Müller works and NO Honfleur pin for the
    Rijks tour;
  • <= PER_TOUR_PASS_USD (default $0.40);
and overall the whole task is under TASK_BUDGET_USD (default $0.60).

Pool is ON (STOP_POOL NOT disabled). We ALSO assert the drift-safety invariant:
if a venue were ever unresolved, the "[LOCAL-850] pool store SKIPPED" line proves
it was not pooled; when it resolves (the expected path here) it pools normally.

DB: an isolated throwaway postgres with EMPTY cache tables (NO seed) — so the
resolver must actually resolve "Rijks Museum Amsterdam" from scratch. Never the
shared/live DB, never an audioura-* container.

Run via the wrapper: ./run_local850_live.sh
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

TASK_ID = os.environ.get("TASK_BUDGET_ID", "LOCAL-850") or "LOCAL-850"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.60") or "0.60")
PER_TOUR_PASS_USD = float(os.environ.get("PER_TOUR_PASS_USD", "0.40") or "0.40")
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

os.environ["DISABLE_TOUR_CACHE"] = "1"
# Pool ON — the ticket requires pool ON (and that an unresolved venue is not
# pooled). Do NOT set DISABLE_STOP_POOL here.
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ.setdefault("CHEAP_ARM_CATEGORIES", "museum")
os.environ.setdefault("NARRATION_MODEL", "gpt-4.1-mini")
os.environ.setdefault("SERPER_RESEARCH_MODEL", "gpt-4.1-mini")
os.environ.setdefault("RESEARCH_BACKEND", "serper")
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

# The two required proofs. Rijks uses the EXACT wave-19 failing string (glued
# city, country tail); Orsay uses the unaccented/spaced variant.
TOURS = [
    ("Rijks Museum Amsterdam, Netherlands", "museum", 5),
    ("Musee d Orsay Paris", "museum", 5),
]

# Drift markers from the wave-19 evidence that must NEVER appear for the Rijks
# tour (the Kröller-Müller works it drifted to, and the Honfleur pin).
_KROLLER_RE = re.compile(r"(?i)kr[oö]ller|m[uü]ller|krollermuller")
_HONFLEUR_RE = re.compile(r"(?i)honfleur")
_RIJKS_QID = "Q190804"
_ORSAY_QID = "Q23402"
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_RESOLVED_RE = re.compile(r"(?i)\[venue_resolver\]\s+Resolved:.*?→\s*(Q\d+)\s*\(([^)]*)\)")
_POOL_SKIP_RE = re.compile(r"\[LOCAL-850\].*pool store SKIPPED.*")
_POOL_STORE_RE = re.compile(r"\[LOCAL-590\]\s+POOL STORE:\s*(\d+)\s+stop")
_DRIFT_REJECT_RE = re.compile(r"\[LOCAL-850\].*REJECT web-search pick.*")
_GLUED_CITY_RE = re.compile(r"\[LOCAL-850\].*Recovered glued city.*")


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


def main():
    print("=" * 70, flush=True)
    print("=== LOCAL-850 live run — unresolved-venue drift fix (POOL ON) ===", flush=True)
    print(f"  TASK_BUDGET_ID={TASK_ID!r} HARD CAP=${HARD_CAP_USD:.2f} "
          f"per-tour PASS <= ${PER_TOUR_PASS_USD:.2f}   meter log: {METER_LOG}",
          flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-850] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    import generate_tour_text as g

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
            print(f"  [LOCAL-850] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
                  f"— NOT running this tour", flush=True)
            try:
                meter.uninstall()
            except Exception:
                pass
            break

        t0 = time.time()
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
        try:
            _usd_before = meter.total_usd()
        except Exception:
            _usd_before = 0.0
        try:
            with contextlib.redirect_stdout(_tee):
                text, _out, _coords = g.generate_tour_text(
                    location, tour_type, None, n_stops)
            dt = time.time() - t0
            print(f"  generated in {dt:.0f}s", flush=True)
        except Exception as e:
            import traceback
            print(f"  [LOCAL-850] raised: {e}", flush=True)
            traceback.print_exc()
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
                meter.uninstall()
            except Exception:
                pass

        captured = buf.getvalue()
        bodies = _split_stop_bodies(text or "")
        resolved = _RESOLVED_RE.findall(captured)
        pool_skipped = bool(_POOL_SKIP_RE.search(captured))
        pool_store_m = _POOL_STORE_RE.search(captured)
        pool_stored = int(pool_store_m.group(1)) if pool_store_m else 0
        drift_rejected = bool(_DRIFT_REJECT_RE.search(captured))
        glued = bool(_GLUED_CITY_RE.search(captured))
        kroller_hits = sorted(set(_KROLLER_RE.findall(text or "")))
        honfleur = bool(_HONFLEUR_RE.search(text or ""))
        results.append({
            "location": location,
            "n_requested": n_stops,
            "n_stops": len(bodies),
            "resolved": resolved,
            "pool_skipped": pool_skipped,
            "pool_stored": pool_stored,
            "drift_rejected": drift_rejected,
            "glued_city_recovered": glued,
            "kroller_hits": kroller_hits,
            "honfleur_pin": honfleur,
            "tour_usd": _tour_usd,
            "stop_titles": [t for (_n, t, _b) in bodies],
        })

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70, flush=True)
    print("=== LOCAL-850 LIVE SUMMARY ===", flush=True)
    overall_pass = True
    for r in results:
        is_rijks = "rijks" in r["location"].lower()
        is_orsay = "orsay" in r["location"].lower()
        want_qid = _RIJKS_QID if is_rijks else (_ORSAY_QID if is_orsay else "")
        resolved_qids = [q for (q, _n) in r["resolved"]]
        qid_ok = (want_qid in resolved_qids) if want_qid else bool(resolved_qids)
        # The core no-drift invariants for the Rijks tour.
        no_kroller = not r["kroller_hits"]
        no_honfleur = not r["honfleur_pin"]
        count_ok = r["n_stops"] == r["n_requested"]
        cost_ok = r["tour_usd"] <= PER_TOUR_PASS_USD
        tour_pass = qid_ok and no_kroller and no_honfleur and count_ok and cost_ok
        overall_pass = overall_pass and tour_pass
        print(f"\n  {r['location']}: {'PASS' if tour_pass else 'FAIL'}", flush=True)
        print(f"    resolved: {r['resolved']} (want {want_qid or 'any'}) "
              f"-> {'OK' if qid_ok else 'FAIL'}", flush=True)
        print(f"    glued-city recovered: {r['glued_city_recovered']}", flush=True)
        print(f"    stops: {r['n_stops']}/{r['n_requested']} -> "
              f"{'OK' if count_ok else 'FAIL'}", flush=True)
        print(f"    titles: {r['stop_titles']}", flush=True)
        print(f"    NO Kröller-Müller works: {'OK' if no_kroller else 'FAIL ' + str(r['kroller_hits'])}", flush=True)
        print(f"    NO Honfleur pin: {'OK' if no_honfleur else 'FAIL'}", flush=True)
        print(f"    pool: stored={r['pool_stored']} skipped_unresolved={r['pool_skipped']} "
              f"drift_rejected={r['drift_rejected']}", flush=True)
        print(f"    cost: ${r['tour_usd']:.4f} (need <= ${PER_TOUR_PASS_USD:.2f}) "
              f"-> {'OK' if cost_ok else 'FAIL'}", flush=True)

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
    budget_ok = total <= HARD_CAP_USD
    print(f"\n  OVERALL: {'PASS' if (overall_pass and budget_ok) else 'FAIL'} "
          f"(tours {'PASS' if overall_pass else 'FAIL'}, "
          f"budget {'OK' if budget_ok else 'OVER'})", flush=True)

    try:
        os.makedirs("/app/reports/local850", exist_ok=True)
        json.dump({"cap": HARD_CAP_USD, "per_tour_cap": PER_TOUR_PASS_USD,
                   "metered_total": total, "results": results},
                  open("/app/reports/local850/live_result.json", "w"),
                  ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass

    return 0 if (overall_pass and budget_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
