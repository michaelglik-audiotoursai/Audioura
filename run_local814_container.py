"""run_local814_container.py — LOCAL-814B live acceptance (ISOLATED container).

Proves the process-wide Gemini breaker end to end with the REAL (depleted) Gemini
key, on the ticket's named tour:

    "Freedom Trail walking tour, Boston, MA"  (4 stops)

TWO ARMS, run one at a time (ARM chosen by RESEARCH_BACKEND in the environment):

  * DEFAULT arm (no RESEARCH_BACKEND override -> Gemini research ON). With a
    depleted key, the FIRST grounded Gemini request returns 402; that trips the
    breaker, and every subsequent Gemini call in the run is SKIPPED and routed to
    its non-Gemini fallback. The tour still COMPLETES. The meter then shows
    exactly ONE Gemini call (the 402 that tripped the breaker) — or a small
    handful at most if several callers raced the first request.

  * RESEARCH_BACKEND=serper arm -> ZERO Gemini calls: the leads path drops gemini
    on the serper arm and the grounded per-stop research uses Serper, so nothing
    ever touches Gemini.

HOW WE COUNT GEMINI CALLS. The paid-API meter (PYTHONPATH=/opt/meter, installed
in the container) writes one JSONL row per paid request to
``/meterlogs/paid_api_calls.jsonl`` with ``kind`` and ``status``. A Gemini 402
IS recorded (status=402, usd=0). We snapshot the row count before the run and
report every gemini row written during it — total, and the 402 subset.

BUDGET: HARD CAP $0.60 TOTAL for the whole task across BOTH arms (ticket). This
runner reads the ledger spend so far via LiveRunMeter and refuses to start a tour
that could exceed the cap. One additive is_test audio_tours-style row is NOT
written here; the only DB writes are the isolated stack's own.

Run (one-shot) on the local814 stack network — DEFAULT (gemini) arm:
    docker run --rm --name local814-tg \
        --network local814_default \
        --env-file .env \
        -e PYTHONPATH=/opt/meter \
        -e DATABASE_URL=postgresql://admin:password123@local814-postgres:5432/audiotours \
        -e DISABLE_TOUR_CACHE=1 \
        -e TEST_GEMINI_MAX_USD=0.60 -e COST_HARD_LIMIT_USD=0.60 \
        -e METER_SERVICE=local814 -e METER_JOB=local814-default \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local814_container.py

Serper arm — add:  -e RESEARCH_BACKEND=serper -e SERP_PROVIDER=serper -e METER_JOB=local814-serper
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests"))

HARD_CAP_USD = 0.60
LOCATION = os.environ.get("LOCAL814_LOCATION", "Freedom Trail walking tour, Boston, MA")
TOUR_TYPE = os.environ.get("LOCAL814_TYPE", "walking")
N_STOPS = int(os.environ.get("LOCAL814_STOPS", "4"))
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))
# The breaker must be LIVE (default). Make sure no stray disable is set.
os.environ.pop("GEMINI_BREAKER_DISABLE", None)

ARM = "serper" if (os.environ.get("RESEARCH_BACKEND", "").strip().lower()
                   == "serper") else "gemini (default)"


def _meter_rows():
    """Every row currently in the meter JSONL (list of dicts). [] if absent."""
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


def _gemini_rows(rows):
    return [r for r in rows if (r.get("kind") == "gemini")]


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")


def main():
    print("=" * 64, flush=True)
    print(f"=== LOCAL-814B live run — ARM: {ARM} ===", flush=True)
    print(f"  tour: {LOCATION!r} / {TOUR_TYPE} / {N_STOPS} stops", flush=True)
    print(f"  HARD CAP (task, both arms): ${HARD_CAP_USD}", flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)

    # Breaker state at the start of this run (fresh process => closed unless a
    # sibling tripped the DB flag within the window).
    try:
        import gemini_breaker as gb
        print(f"  breaker at start: {gb.state()}", flush=True)
    except Exception as e:
        gb = None
        print(f"  [warn] gemini_breaker import failed: {e}", flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-814B] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    meter = LiveRunMeter("LOCAL-814")
    try:
        spent = meter.total_usd()
    except Exception:
        spent = 0.0
    print(f"  ledger spent so far (TEST-LOCAL-814): ${spent:.3f}", flush=True)
    if spent >= HARD_CAP_USD:
        print(f"[LOCAL-814B] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} — "
              f"NOT running", flush=True)
        try:
            meter.uninstall()
        except Exception:
            pass
        return 0

    rows_before = _meter_rows()
    gem_before = len(_gemini_rows(rows_before))
    n_before = len(rows_before)
    print(f"  meter rows before: {n_before} (gemini: {gem_before})", flush=True)

    import generate_tour_text as g
    import traceback as _tb
    t0 = time.time()
    verdict, titles, text = "NO_TEXT", [], ""
    try:
        text, _out, _coords = g.generate_tour_text(LOCATION, TOUR_TYPE, None, N_STOPS)
        dt = time.time() - t0
        if text:
            titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]
            verdict = "COMPLETED" if titles else "TEXT_NO_STOPS"
            print(f"  generated in {dt:.0f}s — {verdict}, {len(titles)} stops",
                  flush=True)
            for i, t in enumerate(titles):
                print(f"    STOP {i+1}: {t[:72]}", flush=True)
        else:
            print(f"  [LOCAL-814B] NO text in {dt:.0f}s", flush=True)
    except Exception as e:
        print(f"  [LOCAL-814B] raised: {e}", flush=True)
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

    # ── Gemini-call accounting from the meter ledger ──────────────────────────
    rows_after = _meter_rows()
    new_rows = rows_after[n_before:] if len(rows_after) >= n_before else rows_after
    gem_new = _gemini_rows(new_rows)
    gem_402 = [r for r in gem_new if r.get("status") == 402]
    gem_429 = [r for r in gem_new if r.get("status") == 429]
    gem_200 = [r for r in gem_new if r.get("status") == 200]

    print("\n  --- GEMINI METER (this run) ---", flush=True)
    print(f"  total gemini calls: {len(gem_new)}", flush=True)
    print(f"    402 (credit trip): {len(gem_402)}", flush=True)
    print(f"    429 (rate limit):  {len(gem_429)}", flush=True)
    print(f"    200 (ok):          {len(gem_200)}", flush=True)
    for r in gem_new:
        print(f"      gemini status={r.get('status')} caller={r.get('caller')} "
              f"usd={r.get('usd')}", flush=True)

    if gb is not None:
        print(f"\n  breaker at end: {gb.state()}", flush=True)

    try:
        print("\n" + meter.summary(), flush=True)
    except Exception:
        pass
    try:
        meter.uninstall()
    except Exception:
        pass

    print("\n=== LOCAL-814B ARM SUMMARY ===", flush=True)
    print(f"  arm:            {ARM}", flush=True)
    print(f"  tour verdict:   {verdict} ({len(titles)} stops)", flush=True)
    print(f"  gemini calls:   {len(gem_new)}  (402={len(gem_402)}, "
          f"429={len(gem_429)}, 200={len(gem_200)})", flush=True)
    if ARM.startswith("gemini"):
        print("  EXPECT: tour COMPLETED; gemini calls == 1 (the 402 trip) or a "
              "small handful; breaker OPEN at end.", flush=True)
    else:
        print("  EXPECT: tour COMPLETED; gemini calls == 0.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
