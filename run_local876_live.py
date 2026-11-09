#!/usr/bin/env python3
"""run_local876_live.py — LOCAL-876 live proof (Mac-local, OWN container).

ONE live 3-stop walking tour through the real generation path from THIS worktree,
against this task's OWN isolated postgres (never the shared dev DB, never the live
DB, never the shared audioura-* containers). TTS is not called.

Proves FINDING 1 (tour 544): the Type/Specialty and Specific Examples HEADER
lines of a delivered walking tour do NOT contradict the stop bodies / evidence.
The delivered text is run back through stop_header_consistency.reconcile_stop_headers
as an ORACLE: a consistent tour is a FIXPOINT (reconciling it a second time
changes nothing and reports no contradiction). If the live tour had shipped a
header style that contradicts its body (the tour-544 neo-Romanesque vs neo-Gothic
defect), the oracle would change the text and the run FAILS.

Launch (the meter reads the budget env at interpreter start):

  TASK_BUDGET_ID=LOCAL-876 TASK_BUDGET_USD=0.15 \\
  python3 run_local876_live.py

Run logs go to ./_local876_meterlogs/ (never committed).
"""
import contextlib
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "tests"))


def _load_dotenv():
    try:
        with open(os.path.join(_HERE, ".env"), "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

if os.environ.get("TASK_BUDGET_ID") != "LOCAL-876":
    sys.exit("refusing to run: launch with TASK_BUDGET_ID=LOCAL-876 (see docstring)")
_TASK_ID = os.environ["TASK_BUDGET_ID"]
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.15") or "0.15")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

# OWN isolated postgres (docker container local876-pg, mapped to localhost).
_OWN_DB = os.environ.get(
    "LOCAL876_DB_URL", "postgresql://admin:password123@localhost:55876/audiotours")
for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB)):
    os.environ[_k] = _v
os.environ.pop("K_SERVICE", None)

os.environ["LANDMARK_LIVE_LOOKUP"] = "1"
os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
os.environ["STORY_PASS_MODEL"] = "gpt-4.1"
os.environ["RESEARCH_BACKEND"] = "serper"
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")

_METER_DIR = os.path.join(_HERE, "_local876_meterlogs")
os.makedirs(_METER_DIR, exist_ok=True)

# Tour 544's venue (HCMC), 3 stops: the Notre-Dame Cathedral Basilica of Saigon
# is stop 1, where the neo-Romanesque/neo-Gothic header defect appeared.
REQUEST = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"
N_STOPS = 3

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")


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


def _check(label, ok, detail=""):
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}: {detail}", flush=True)
    return bool(ok)


def main():
    from live_run_meter import LiveRunMeter
    _lrm = LiveRunMeter(_TASK_ID, cap_usd=HARD_CAP_USD)
    import generate_tour_text as g
    import stop_header_consistency as shc

    print(f"\n[LOCAL-876] request={REQUEST!r}; {N_STOPS} stops; cap ${HARD_CAP_USD:.2f}",
          flush=True)
    buf = io.StringIO()
    text = ""
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(REQUEST, "walking", None, N_STOPS)
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    log = buf.getvalue()
    open(os.path.join(_METER_DIR, "tour.txt"), "w", encoding="utf-8").write(text or "")
    open(os.path.join(_METER_DIR, "log.txt"), "w", encoding="utf-8").write(log)
    try:
        _lrm.add_generation(g)
    except Exception:
        pass
    try:
        _row = _lrm.record()
        print(f"\n[LOCAL-876] cost ledger row: {_row}", flush=True)
    except Exception as _me:
        print(f"[LOCAL-876] meter.record failed: {_me}", flush=True)
    try:
        print(_lrm.summary(), flush=True)
    except Exception:
        pass
    try:
        _spend = _lrm.combined_spend_usd()
    except Exception:
        _spend = None
    try:
        _lrm.uninstall()
    except Exception:
        pass

    ok = _check("tour text produced", bool(text and text.strip()),
                f"{len(text or '')} chars")
    if not text:
        print("=== LOCAL-876 FAIL (no text) ===", flush=True)
        return False

    stops = _STOP_HEADER_RE.findall(text)
    ok &= _check("at least 3 stops delivered", len(stops) >= 3, len(stops))

    # Show the header lines actually delivered.
    print("\n--- delivered header lines ---", flush=True)
    for ln in text.split("\n"):
        if re.match(r"(?i)^(Type/Specialty|Specific Examples):", ln.strip()):
            print("  " + ln.strip(), flush=True)
    print("------------------------------\n", flush=True)

    # Report any [LOCAL-876] reconcile telemetry the run itself emitted.
    recon = re.findall(r"\[LOCAL-876\].*", log)
    if recon:
        print("--- [LOCAL-876] reconcile telemetry (during generation) ---", flush=True)
        for ln in recon:
            print("  " + ln, flush=True)
        print("-----------------------------------------------------------\n", flush=True)

    # ORACLE: the delivered text must be a FIXPOINT of the header reconciler —
    # reconciling it again changes NOTHING (no residual header-vs-body style
    # contradiction shipped). This is the direct proof the header lines are
    # consistent with the bodies.
    reconciled = shc.reconcile_stop_headers(text, poi_list=None)
    ok &= _check("delivered header lines are consistent (reconcile is a fixpoint)",
                 reconciled == text,
                 "no change" if reconciled == text else "RESIDUAL CONTRADICTION")

    # Belt and braces: no stop ships BOTH neo-Romanesque and neo-Gothic in its
    # header + body (the exact tour-544 defect).
    low = text.lower()
    clash544 = ("neo-romanesque" in low and "neo-gothic" in low and
                reconciled != text)
    ok &= _check("no neo-Romanesque/neo-Gothic header-vs-body clash shipped",
                 not clash544, "clean")

    print(f"\n   task spend: "
          f"{('$%.4f' % _spend) if _spend is not None else '(see meter log)'} "
          f"of ${HARD_CAP_USD:.2f}", flush=True)
    print(f"=== LOCAL-876 {'PASS' if ok else 'FAIL'} ===", flush=True)
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
