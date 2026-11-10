#!/usr/bin/env python3
"""meter_guard.py — LOCAL-888: a paid run must never be recorded as $0.

LEAD ran the parity harness from a detached worktree with PYTHONPATH=<wt>/_meter.
sitecustomize imported ``paid_api_meter`` at interpreter start, when PAID_API_LOG was
not yet exported, so the module froze ``LOG = /meterlogs/paid_api_calls.jsonl``. The
harness only did ``os.environ.setdefault("PAID_API_LOG", ...)`` later, which the
already-imported module never re-read: the run made dozens of paid calls, the
harness's own meter file stayed empty, and it printed ``run metered $0.0000``.

Two defences:

  * ``repoint_meter_log(path)`` points the live meter module at the harness's log.
  * ``check_meter(...)`` compares what the meter captured with what the run's own
    log proves it did (one gate call per ``grounding <stop>: labelled`` line, one
    per ``NARRATED`` rebuild, one per audit). Fewer rows than that means the meter
    missed paid calls: the result says so LOUDLY and carries a CONSERVATIVE
    estimate, which the caller records in the ledger instead of the metered $.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, Tuple

# Conservative per-call estimates (USD), deliberately above the observed means.
EST_GATE_CALL = 0.004
EST_NARRATE_CALL = 0.003
EST_AUDIT_CALL = 0.06
EST_FLOOR_IF_UNMETERED = 0.08          # a full-tour run is never cheaper than this

_GATE_LINE = re.compile(r"\[LOCAL-883\]\s+grounding\s+.+?:\s+labelled\b")
_NARRATED_LINE = re.compile(r"\[LOCAL-873C\].*\bNARRATED\b")
_COHERENCE_LINE = re.compile(r"\[LOCAL-888\]\s+coherence\s+.+?issues\s+[1-9]")


def repoint_meter_log(path: str) -> bool:
    """Export PAID_API_LOG and re-point an already-imported ``paid_api_meter`` at
    it. Returns True when a live meter module was found and re-pointed."""
    os.environ["PAID_API_LOG"] = path
    mod = sys.modules.get("paid_api_meter")
    if mod is None:
        return False
    try:
        mod.LOG = path
        return True
    except Exception:
        return False


def meter_rows(path: str, skip_rows: int = 0) -> Tuple[int, float]:
    """(rows, usd) in the meter log after the first ``skip_rows`` rows."""
    rows, total = 0, 0.0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i < skip_rows:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                rows += 1
                total += float(r.get("usd", r.get("cost_usd", r.get("cost", 0))) or 0)
    except FileNotFoundError:
        pass
    return rows, total


def count_rows(path: str) -> int:
    return meter_rows(path)[0]


def logged_calls(run_log: str, audit_ran: bool = True) -> Dict[str, int]:
    """Paid calls the run's own log proves it made (a lower bound)."""
    text = run_log or ""
    return {
        "gate": len(_GATE_LINE.findall(text)),
        "narrate": len(_NARRATED_LINE.findall(text)),
        "coherence": len(_COHERENCE_LINE.findall(text)),
        "audit": 1 if audit_ran else 0,
    }


def estimate_usd(calls: Dict[str, int]) -> float:
    return round(calls.get("gate", 0) * EST_GATE_CALL
                 + calls.get("narrate", 0) * EST_NARRATE_CALL
                 + calls.get("coherence", 0) * EST_NARRATE_CALL
                 + calls.get("audit", 0) * EST_AUDIT_CALL, 6)


def check_meter(rows_captured: int, usd_captured: float, run_log: str,
                audit_ran: bool = True) -> Dict:
    """Verdict on a finished run.

    ``ok`` is False when the meter captured fewer rows than the log's gate +
    narrate + audit lines prove (or captured nothing for a run that clearly made
    calls). ``record_usd`` is what the caller must write to the budget ledger: the
    metered $ when the meter is sound, else max(metered, conservative estimate,
    floor). Never returns less than the metered $."""
    calls = logged_calls(run_log, audit_ran)
    expected_rows = calls["gate"] + calls["narrate"] + calls["audit"]
    est = estimate_usd(calls)
    ok = rows_captured >= expected_rows and not (expected_rows > 0 and rows_captured == 0)
    if ok:
        return {"ok": True, "record_usd": round(usd_captured, 6), "estimate_usd": est,
                "expected_rows": expected_rows, "rows": rows_captured,
                "message": f"meter ok: {rows_captured} rows >= {expected_rows} logged calls"}
    record = round(max(usd_captured, est, EST_FLOOR_IF_UNMETERED if expected_rows else 0.0), 6)
    return {"ok": False, "record_usd": record, "estimate_usd": est,
            "expected_rows": expected_rows, "rows": rows_captured,
            "message": (f"METER FAILURE: captured {rows_captured} row(s) (${usd_captured:.4f}) "
                        f"but the run log shows >= {expected_rows} paid call(s) "
                        f"({calls}). Recording the conservative estimate "
                        f"${record:.4f} instead of the metered amount.")}
