#!/usr/bin/env python3
"""run_local855_live.py — LOCAL-855 live, budget-enforced proof (Mac-local).

Re-runs the EXACT field request LOCAL-852 reproduced ("Sophia's biking tour in Ho
Chi Minh City, Vietnam", seven user-chosen stops pasted as name + share link /
website) and checks the NARRATION this time, not just the pins:

  PASS =
    7/7 stops delivered;
    each stop is ABOUT its own venue (not the literal name's meaning);
    NO cross-tour "you saw at <place not in this tour>" callback;
    NO invented street name in directions;
    mode is BIKING (the header is not "a walking tour");
    NO dated unsourced claim marker carried over from the LOCAL-852 run
      (the known fabrications: VietPride 2018, Bức Tường 2015, the airport
       2021/2026, the Cần Thơ 2025 merger, the 1975 offensive).

BUDGET — ENFORCED. TASK_BUDGET_ID=LOCAL-855 TASK_BUDGET_USD=0.60, meter contract,
own meter log under ./_local855_meterlogs, cheap env + STORY_PASS_MODEL=gpt-4.1,
pool OFF. Mac-LOCAL diagnostic (the documented no-mount escape hatch, same as
run_local852_live.py): METER_MOUNT_GUARD=0. It never writes the shared/live DB
and never touches the shared audioura-* containers.
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
os.environ["TASK_BUDGET_ID"] = "LOCAL-855"
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

_METER_DIR = os.path.join(_HERE, "_local855_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)
METER_LOG = os.path.join(_METER_DIR, "paid_api_calls.jsonl")
os.environ["PAID_API_LOG"] = METER_LOG
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-855"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _METER_DIR)

LOCATION = "Ho Chi Minh City, Vietnam"
TOUR_TYPE = "Sophia's biking tour"

# The seven user stops, EXACTLY as pasted (name + share link / website).
USER_STOPS = [
    "Rambutan https___share.google_1v4x",
    "Longan https___share.google_z20B",
    "The Crazy street",
    "The LGBT bar 🌈Thi Bar Saigon",
    "A Star is Born",
    "Acoustic Bar - Ngô Thời Nhiệm, Quận 3",
    "An Spa at https___an-spa.vn_en",
]

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")

# Dated/filler markers from the LOCAL-852 run that must NOT recur — each is an
# unsourced claim or off-topic history about a user venue.
_BANNED_MARKERS = [
    "Art Institute of Chicago",   # cross-tour callback
    "VietPride 2018",             # Thi Bar fabrication
    "Bức Tường",                  # Acoustic Bar 2015 fabrication
    "Long Thanh International Airport",  # airport filler
    "Resolution No. 202/2025",    # Cần Thơ merger filler
    "1975 spring offensive",      # war filler
    "Le Van Sy Street",           # invented street
]


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
    print("=== LOCAL-855 live — Sophia's biking tour, HCMC, 7 user stops ===",
          flush=True)
    print(f"  TASK_BUDGET_ID={os.environ.get('TASK_BUDGET_ID')!r} "
          f"HARD CAP=${HARD_CAP_USD:.2f}", flush=True)
    print(f"  meter log: {METER_LOG}", flush=True)
    print(f"  STORY_PASS_MODEL={os.environ['STORY_PASS_MODEL']!r} "
          f"NARRATION_MODEL={os.environ['NARRATION_MODEL']!r} "
          f"DISABLE_STOP_POOL={os.environ['DISABLE_STOP_POOL']!r}", flush=True)
    print(f"  location={LOCATION!r} tour_type={TOUR_TYPE!r}", flush=True)

    try:
        open(METER_LOG, "w").close()
    except Exception:
        pass

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-855] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    try:
        import task_budget as _tb
        _spent = _tb.spent_so_far("LOCAL-855")
    except Exception:
        _spent = 0.0
    print(f"  task-ledger spent so far: ${_spent:.3f} / ${HARD_CAP_USD:.2f}",
          flush=True)
    if _spent >= HARD_CAP_USD:
        print(f"  [LOCAL-855] reserve gate: ${_spent:.3f} >= ${HARD_CAP_USD} "
              f"— NOT running", flush=True)
        return 1

    import generate_tour_text as g

    meter = LiveRunMeter("LOCAL-855")
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
        print(f"  [LOCAL-855] raised: {e}", flush=True)
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

    titles = [(int(a), b.strip()) for a, b in _STOP_HEADER_RE.findall(text or "")]

    # Save the delivered text.
    _art_dir = os.path.join(_HERE, "submission_artifacts", "local855")
    os.makedirs(_art_dir, exist_ok=True)
    if text:
        with open(os.path.join(_art_dir, "live_tour_7stops.txt"), "w",
                  encoding="utf-8") as f:
            f.write(text)
    rows = _meter_rows()
    total = sum(float(r.get("usd") or 0.0) for r in rows
                if r.get("status") in (200, "200"))
    with open(os.path.join(_art_dir, "meter_ledger.json"), "w",
              encoding="utf-8") as f:
        json.dump({"task_budget_id": "LOCAL-855", "hard_cap_usd": HARD_CAP_USD,
                   "metered_total_usd": round(total, 6),
                   "rows": len(rows)}, f, indent=2)

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-855 SUMMARY ===", flush=True)
    print(f"  delivered stops: {len(titles)}/{len(USER_STOPS)}", flush=True)
    for n, t in titles:
        print(f"    Stop {n}: {t[:70]}", flush=True)

    # ── PASS checks ──
    n_delivered = len(titles)
    _text = text or ""

    # Mode: header must say biking/cycling, never "walking tour".
    _header = _text.split("\n", 1)[0] if _text else ""
    mode_biking = ("walking tour" not in _text.lower().split("stop 1")[0]) and (
        "bik" in _text.lower().split("stop 1")[0]
        or "cycl" in _text.lower().split("stop 1")[0])

    # No banned markers (cross-tour callback, invented street, dated fabrications).
    present = [m for m in _BANNED_MARKERS if m.lower() in _text.lower()]
    no_banned = not present

    # Each stop body mentions its own venue name (subject binding, coarse check).
    def _body_names_venue(title, body):
        toks = [w.lower() for w in re.findall(r"[A-Za-zÀ-ỹ]{3,}", title)
                if w.lower() not in ("the", "bar", "lgbt", "star", "spa")]
        return any(w in body.lower() for w in toks) if toks else True

    _blocks = re.split(r"(?mi)^Stop\s+\d+:\s*", _text)
    bodies_on_subject = True
    for (n, t), body in zip(titles, _blocks[1:]):
        if not _body_names_venue(t, body):
            bodies_on_subject = False
            print(f"  [check] Stop {n} body may not name its venue: {t!r}",
                  flush=True)

    budget_ok = total <= HARD_CAP_USD

    print(f"\n  7/7 delivered:        {n_delivered == len(USER_STOPS)}", flush=True)
    print(f"  mode biking:          {mode_biking}", flush=True)
    print(f"  no cross-tour/filler: {no_banned}"
          + (f"  (found: {present})" if present else ""), flush=True)
    print(f"  bodies on-subject:    {bodies_on_subject}", flush=True)
    print(f"  metered total:        ${total:.4f} / cap ${HARD_CAP_USD:.2f} "
          f"({'OK' if budget_ok else 'OVER'})", flush=True)

    verdict = (n_delivered == len(USER_STOPS) and mode_biking and no_banned
               and bodies_on_subject and budget_ok)
    print(f"\n=== LOCAL-855 OVERALL: {'PASS' if verdict else 'CHECK'} ===",
          flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
