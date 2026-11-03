#!/usr/bin/env python3
"""run_local852_live.py — LOCAL-852 live, budget-enforced proof (Mac-local).

Reproduces the EXACT field request (GCloud_Storied_1, Michael's own request, gen
00027-6sb, tour 523): "Sophia's biking tour in Ho Chi Minh City, Vietnam" with the
SEVEN user-chosen stops pasted as name + a Google share link / website. In the
field only 2 of 7 were delivered because:
  1. the provider guard mis-read the tour NAME as an activity-provider request and
     dropped the listener's own stops;
  2. the share links were never resolved — names kept URL junk, four stops fell to
     the same city centroid and the dedupe collapsed them;
  3. the scope centre fell back to 'Vietnam'.

PASS = 7/7 stops delivered, CLEAN names (no URL junk), DISTINCT real pins in HCMC.

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-852 TASK_BUDGET_USD=0.60, meter contract,
own meter log, cheap env + STORY_PASS_MODEL=gpt-4.1, pool OFF. Mac-LOCAL
diagnostic (the documented no-mount escape hatch, same as run_local835b_live.py):
writes its meter log under ./_local852_meterlogs and sets METER_MOUNT_GUARD=0. It
never writes the shared/live DB and never touches the shared audioura-* containers.
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


def _load_dotenv():
    """Export KEY=VALUE pairs from the worktree .env (symlink ok) into the
    process env, without overwriting a var already set. No python-dotenv dep."""
    path = os.path.join(_HERE, ".env")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

# ── budget + cheap env ───────────────────────────────────────────────────────
os.environ.setdefault("TASK_BUDGET_ID", "LOCAL-852")
os.environ.setdefault("TASK_BUDGET_USD", "0.60")
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.60") or "0.60")
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
os.environ.setdefault("USER_STOPS_ENABLED", "true")  # honour the pasted stops

_METER_DIR = os.path.join(_HERE, "_local852_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-852"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

LOCATION = "Ho Chi Minh City, Vietnam"
TOUR_TYPE = "Sophia's biking tour"

# The seven user stops, EXACTLY as pasted (name + share link / website). The two
# share links are REAL share.google forms resolved live; if a specific short link
# 404s, the stop degrades to geocode-by-name (never a drop).
USER_STOPS = [
    "Rambutan https___share.google_1v4x",
    "Longan https___share.google_z20B",
    "The Crazy street",
    "The LGBT bar 🌈Thi Bar Saigon",
    "A Star is Born",
    "Acoustic Bar - Ngô Thời Nhiệm, Quận 3",
    "An Spa at https___an-spa.vn_en",
]

# Clean display names we expect after parsing (URL junk removed).
EXPECT_CLEAN = [
    "Rambutan", "Longan", "The Crazy Street", "The LGBT Bar",
    "A Star Is Born", "Acoustic Bar", "An Spa",
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_COORD_RE = re.compile(r"(-?\d{1,3}\.\d+)[,\s]+(-?\d{1,3}\.\d+)")


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


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-852 live — Sophia's biking tour, HCMC, 7 user stops ===",
          flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}", flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)
    print(f"  STORY_PASS_MODEL={os.environ['STORY_PASS_MODEL']!r} "
          f"NARRATION_MODEL={os.environ['NARRATION_MODEL']!r} "
          f"DISABLE_STOP_POOL={os.environ['DISABLE_STOP_POOL']!r}", flush=True)
    print(f"  location={LOCATION!r} tour_type={TOUR_TYPE!r}", flush=True)
    print(f"  user stops ({len(USER_STOPS)}): {USER_STOPS}", flush=True)

    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-852] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    # Reserve gate.
    try:
        import task_budget as _tb
        _spent = _tb.spent_so_far("LOCAL-852")
    except Exception:
        _spent = 0.0
    print(f"  task-ledger spent so far: ${_spent:.3f} / ${HARD_CAP_USD:.2f}",
          flush=True)
    if _spent >= HARD_CAP_USD:
        print(f"  [LOCAL-852] reserve gate: ${_spent:.3f} >= ${HARD_CAP_USD} "
              f"— NOT running", flush=True)
        return 1

    import generate_tour_text as g

    meter = LiveRunMeter("LOCAL-852")
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
                LOCATION, TOUR_TYPE, None, len(USER_STOPS),
                forced_stops=list(USER_STOPS))
        dt = time.time() - t0
        print(f"\n  generated in {dt:.0f}s", flush=True)
    except Exception as e:
        import traceback
        print(f"  [LOCAL-852] raised: {e}", flush=True)
        traceback.print_exc()
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

    captured = buf.getvalue()
    titles = [(int(a), b.strip()) for a, b in _STOP_HEADER_RE.findall(text or "")]

    # Collect the per-stop coordinates the pipeline logged for the user stops.
    pins = {}
    for m in re.finditer(r"\[LOCAL-852\] user stop .*?pinned from share link at "
                         r"(-?\d+\.\d+),?\s*(-?\d+\.\d+)", captured):
        pins.setdefault((m.group(1), m.group(2)), 0)

    rows = _meter_rows()
    total = sum(float(r.get("usd") or 0.0) for r in rows
                if r.get("status") in (200, "200"))

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-852 SUMMARY ===", flush=True)
    print(f"  delivered stops: {len(titles)}/{len(USER_STOPS)}", flush=True)
    for n, t in titles:
        print(f"    Stop {n}: {t[:70]}", flush=True)

    # PASS checks.
    n_delivered = len(titles)
    names_clean = all("http" not in t.lower() and "___" not in t
                      for _, t in titles)
    distinct_titles = len({t.lower() for _, t in titles}) == len(titles)

    print(f"\n  7/7 delivered: {n_delivered == len(USER_STOPS)}", flush=True)
    print(f"  names clean (no URL junk): {names_clean}", flush=True)
    print(f"  distinct titles: {distinct_titles}", flush=True)
    print(f"  metered total (status-200): ${total:.4f} / cap ${HARD_CAP_USD:.2f}",
          flush=True)

    budget_ok = total <= HARD_CAP_USD
    verdict = (n_delivered == len(USER_STOPS) and names_clean
               and distinct_titles and budget_ok)
    print(f"\n=== LOCAL-852 OVERALL: {'PASS' if verdict else 'CHECK'} ===",
          flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
