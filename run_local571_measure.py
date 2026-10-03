#!/usr/bin/env python3
"""LOCAL-571 step 2 — writer-model blind test: gpt-4o vs gpt-4.1.

The gpt-4o stop writer is 81% of LLM cost (D596). Its model is already an env
knob: TOUR_STORY_MODEL (generate_tour_text.py:195, default gpt-4o). LOCAL-560
ruled out gpt-3.5 (cannot sustain a sourced story). P2 (LOCAL-566 §3): gpt-4.1
may be ~20% cheaper at similar quality. This harness measures both arms on four
requests, one run each, so a human can judge quality blind (step 3).

Two arms, one run each (LOCAL-569 flags STAY OFF in both — never set):
  A  TOUR_STORY_MODEL=gpt-4o   (today / ship default)
  B  TOUR_STORY_MODEL=gpt-4.1

Four requests, 3 stops each (D261 host env, Gemini off as LOCAL-566/569):
  Palais   museum      Palais Lascaris, Nice, France
  MFA      museum      Museum of Fine Arts, Boston, MA
  BosRest  restaurant  restaurant tour of Boston, MA
  OldNice  walking     walking tour of Old Nice, France

Host env (D261): DISABLE_TOUR_CACHE=1, STORIED_MODE=true, DATABASE_URL ->
localhost:5433. Gemini OFF: GEMINI_API_KEY / GOOGLE_API_KEY set to EMPTY before
any import so story_leads's setdefault cannot refill them and the grounding
channel issues zero requests (same technique as run_local569_measure.py).

OpenAI cap: a cumulative $5 budget across all 8 cells, enforced in the loop with
a per-cell headroom guard, plus the per-tour COST_HARD_LIMIT_USD guard. The
harness persists summary.json after every cell, so a partial run is still an
artifact and a re-run resumes (skips cells already marked ok).

Writer isolation: the cost accumulator aggregates ALL OpenAI calls into one
bucket (writer + gates). The gates run on gpt-4o-mini; the WRITER (story pass)
runs on the arm's TOUR_STORY_MODEL. To report "writer calls" and "writer $"
separately from gate spend, this harness wraps cost_accumulator.add_llm_usage to
tally USD + call-count per wire-model for the duration of each cell, then
attributes the arm's story model (gpt-4o in A, gpt-4.1 in B — matched by
substring so dated wire names like gpt-4.1-2025-04-14 count) as the writer.

NO audio_tours writes: generate_tour_text() (the in-process path used here) does
NOT call store_audio_tour. The harness records audio_tours row counts before and
after to prove it, and never DELETEs.

Run:
    python3 run_local571_measure.py              # all remaining cells
    python3 run_local571_measure.py A Palais     # a single cell by arm + request
"""
import contextlib
import io
import json
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))

# --- D261 host env -----------------------------------------------------------
_envfile = os.path.join(HERE, ".env")
if os.path.exists(_envfile):
    for _line in open(_envfile):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ["STORIED_MODE"] = "true"
os.environ.setdefault("DATABASE_URL",
                      "postgresql://admin:password123@localhost:5433/audiotours")
# Gemini off (LOCAL-566): empty (present-but-falsy) BEFORE any import so
# story_leads's setdefault cannot refill a popped key.
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_API_KEY"] = ""
# Per-tour safety guard; the cumulative $5 cap is enforced in the loop below.
os.environ.setdefault("COST_HARD_LIMIT_USD", "2.00")

# LOCAL-569 flags must stay OFF in BOTH arms — ensure they are not inherited.
os.environ.pop("STORY_RETRY_KEEP_BEST", None)
os.environ.pop("STORY_RETRY_EARLY_STOP", None)

OUTDIR = os.path.join(HERE, "LOCAL571_measure")
os.makedirs(OUTDIR, exist_ok=True)
SUMMARY = os.path.join(OUTDIR, "summary.json")

OPENAI_BUDGET_USD = 5.0
# Headroom reserved before starting a new cell. A 3-stop Gemini-off tour has been
# ~$0.3-0.9 of OpenAI in LOCAL-566/569; reserve $1.1 so we never cross $5.
CELL_HEADROOM_USD = 1.1

# (key, tour_type, location)
REQUESTS = [
    ("Palais",  "museum",     "Palais Lascaris, Nice, France"),
    ("MFA",     "museum",     "Museum of Fine Arts, Boston, MA"),
    ("BosRest", "restaurant", "restaurant tour of Boston, MA"),
    ("OldNice", "walking",    "walking tour of Old Nice, France"),
]
# A = ship default; B = candidate. Writer model per arm (what TOUR_STORY_MODEL is
# set to). The gates always run gpt-4o-mini regardless of arm.
ARMS = {
    "A": {"TOUR_STORY_MODEL": "gpt-4o"},
    "B": {"TOUR_STORY_MODEL": "gpt-4.1"},
}
STOPS = 3

_ATTEMPT_RE = re.compile(
    r"\[LOCAL-569\] Stop (\d+) attempt (\d+)/(\d+) story_count=(\d+) words=(\d+)")
_STORYRETRY_RE = re.compile(r"\[LOCAL-432\] Stop (\d+): STORY RETRY")

# Gate rejection lines (counted per arm):
#   LOCAL-235 R10 unfulfilled-promise deletion — per-stop deletions + summary total
_L235_STOP_RE = re.compile(r"\[LOCAL-235\] Stop (\d+) '[^']*': (\d+) ")
_L235_SUMMARY_RE = re.compile(r"\[LOCAL-235\] R10 summary: (\d+) sentences deleted")
#   LOCAL-472 stop-specificity gate — removed paragraphs + ungrounded entities
_L472_REMOVED_RE = re.compile(r"\[LOCAL-472\] REMOVED transferable paragraph")
_L472_UNGROUNDED_RE = re.compile(r"\[LOCAL-472\] UNGROUNDED entity")
#   LOCAL-229 contradicted-claim block — per-group blocks + summary
_L229_BLOCKED_RE = re.compile(r"\[LOCAL-229\] BLOCKED Stop (\d+)")
_L229_SUMMARY_RE = re.compile(r"\[LOCAL-229\] CONTRADICTED block summary: (\d+) group")


def _audio_tours_count():
    try:
        from db_connection import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        total = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(id),0) FROM audio_tours")
        maxid = cur.fetchone()[0]
        conn.close()
        return {"total": total, "max_id": maxid}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _parse_log(log_text):
    """Extract per-attempt story lines, LOCAL-432 retries, and every gate
    rejection line, counted per arm."""
    attempts = {}  # stop -> list of {attempt,of,story_count,words}
    for m in _ATTEMPT_RE.finditer(log_text):
        stop = int(m.group(1))
        attempts.setdefault(stop, []).append({
            "attempt": int(m.group(2)), "of": int(m.group(3)),
            "story_count": int(m.group(4)), "words": int(m.group(5)),
        })
    for stop in attempts:
        attempts[stop].sort(key=lambda d: d["attempt"])
    # shipped story_count per stop = last attempt line for that stop
    shipped = {str(k): v[-1]["story_count"] for k, v in attempts.items() if v}

    l235_stop_hits = _L235_STOP_RE.findall(log_text)
    l235_summary = _L235_SUMMARY_RE.findall(log_text)
    l229_summary = _L229_SUMMARY_RE.findall(log_text)
    return {
        "attempts_by_stop": {str(k): v for k, v in sorted(attempts.items())},
        "shipped_story_count_by_stop": {k: shipped[k] for k in sorted(shipped)},
        "writer_attempts_logged": sum(len(v) for v in attempts.values()),
        "story_retries_432": len(_STORYRETRY_RE.findall(log_text)),
        "gate_235_r10": {
            "per_stop_deletion_events": len(l235_stop_hits),
            "sentences_deleted_total": sum(int(x[1]) for x in l235_stop_hits),
            "summary_reported_total": int(l235_summary[-1]) if l235_summary else 0,
        },
        "gate_472_specificity": {
            "paragraphs_removed": len(_L472_REMOVED_RE.findall(log_text)),
            "ungrounded_entities": len(_L472_UNGROUNDED_RE.findall(log_text)),
        },
        "gate_229_contradicted": {
            "blocked_stop_lines": len(_L229_BLOCKED_RE.findall(log_text)),
            "groups_blocked_summary": int(l229_summary[-1]) if l229_summary else 0,
        },
    }


class _WriterMeter:
    """Wrap cost_accumulator.add_llm_usage to tally USD + calls per wire-model.

    Non-invasive: it delegates to the real function (so the normal per-tour
    accumulator still receives every call and _LAST_GENERATION_COST is correct),
    and additionally records {model -> {calls, usd, input_tokens, output_tokens}}
    for THIS cell. Priced with the same cost_rates table the accumulator uses, so
    the per-model USD split sums to the accumulator's llm total.
    """
    def __init__(self):
        import cost_accumulator as ca
        import cost_rates as cr
        self._ca = ca
        self._cr = cr
        self._orig = ca.add_llm_usage
        self.by_model = {}

    def __enter__(self):
        def _wrapped(input_tokens, output_tokens, model):
            try:
                m = model or "unknown"
                rec = self.by_model.setdefault(
                    m, {"calls": 0, "usd": 0.0, "input_tokens": 0, "output_tokens": 0})
                rec["calls"] += 1
                rec["input_tokens"] += int(input_tokens or 0)
                rec["output_tokens"] += int(output_tokens or 0)
                rec["usd"] += self._cr.llm_cost(
                    input_tokens=int(input_tokens or 0),
                    output_tokens=int(output_tokens or 0),
                    model=m)
            except Exception:
                pass
            return self._orig(input_tokens=input_tokens,
                              output_tokens=output_tokens, model=model)
        self._ca.add_llm_usage = _wrapped
        # openai_cost_wrapper captured a reference to the module function at
        # install time? No — it calls cost_accumulator.add_llm_usage by attribute
        # at call time, so patching the module attribute is enough.
        return self

    def __exit__(self, *exc):
        self._ca.add_llm_usage = self._orig
        return False

    def writer_split(self, writer_model):
        """Sum calls/usd for wire-models that match the arm's writer model.

        Matched by substring so 'gpt-4.1' matches wire 'gpt-4.1-2025-04-14' and
        'gpt-4o' matches 'gpt-4o-2024-08-06' — but NOT 'gpt-4o-mini' (the gate
        model), because we require the writer family and exclude any '-mini'.
        """
        writer_calls = writer_usd = 0
        wi = wo = 0
        other = {}
        for m, rec in self.by_model.items():
            is_writer = (writer_model in m) and ("mini" not in m)
            if is_writer:
                writer_calls += rec["calls"]
                writer_usd += rec["usd"]
                wi += rec["input_tokens"]
                wo += rec["output_tokens"]
            else:
                other[m] = rec
        return {
            "writer_model_requested": writer_model,
            "writer_calls": writer_calls,
            "writer_usd": round(writer_usd, 6),
            "writer_input_tokens": wi,
            "writer_output_tokens": wo,
            "non_writer_by_model": {
                m: {"calls": r["calls"], "usd": round(r["usd"], 6)}
                for m, r in other.items()},
        }


def run_cell(arm, rkey, tour_type, location):
    cell_id = f"{rkey}_{arm}"
    # Set the arm's writer model; keep LOCAL-569 flags OFF.
    os.environ["TOUR_STORY_MODEL"] = ARMS[arm]["TOUR_STORY_MODEL"]
    os.environ.pop("STORY_RETRY_KEEP_BEST", None)
    os.environ.pop("STORY_RETRY_EARLY_STOP", None)

    import importlib
    import generate_tour_text as gtt
    importlib.reload(gtt)

    text_path = os.path.join(OUTDIR, f"{cell_id}.txt")
    buf = io.StringIO()
    t0 = time.time()
    err = None
    text = None
    with _WriterMeter() as meter:
        try:
            with contextlib.redirect_stdout(buf):
                text, _out, _coords = gtt.generate_tour_text(
                    location, tour_type, text_path, STOPS,
                    job_id=f"local571-{cell_id}")
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    wall = time.time() - t0
    log_text = buf.getvalue()
    with open(os.path.join(OUTDIR, f"{cell_id}.log"), "w", encoding="utf-8") as fh:
        fh.write(log_text)

    cost = dict(getattr(gtt, "_LAST_GENERATION_COST", {}) or {})
    acc = cost.get("cost_accumulator") or {}
    llm = (acc.get("llm") or {}) if isinstance(acc, dict) else {}
    breakdown = cost.get("breakdown") or {}
    parsed = _parse_log(log_text)
    writer = meter.writer_split(ARMS[arm]["TOUR_STORY_MODEL"])

    # stops delivered = count of "Stop N:" headers in the delivered text
    stops_delivered = len(re.findall(r"(?mi)^\s*(?:###\s*)?Stop\s+\d+\s*[:\-]", text or ""))
    if stops_delivered == 0:
        stops_delivered = len(re.findall(r"Stop\s+\d+\s*:", text or ""))

    score = {}
    try:
        import tour_quality as tq
        scored = tq.score_tour(text or "", STOPS, is_building_tour=False)
        score = {
            "clean": scored.get("clean"),
            "defects": list(scored.get("defects", {}).keys()),
            "defect_detail": scored.get("defects", {}),
            "metrics": scored.get("metrics", {}),
        }
    except Exception as e:
        score = {"error": f"{type(e).__name__}: {e}"}

    rec = {
        "cell": cell_id, "arm": arm, "request": rkey, "tour_type": tour_type,
        "location": location, "writer_model": ARMS[arm]["TOUR_STORY_MODEL"],
        "ok": bool(text) and err is None, "error": err,
        "wall_s": round(wall, 1), "chars": len(text or ""),
        "stops_delivered": stops_delivered,
        # writer isolation
        "writer_calls": writer["writer_calls"],
        "writer_usd": writer["writer_usd"],
        "writer_input_tokens": writer["writer_input_tokens"],
        "writer_output_tokens": writer["writer_output_tokens"],
        "non_writer_llm_by_model": writer["non_writer_by_model"],
        # full ledger (writer + gates + search + grounding)
        "all_llm_calls": llm.get("calls"),
        "breakdown_llm_usd": round(breakdown.get("llm", 0.0), 6),
        "search_usd": round(breakdown.get("search", 0.0), 6),
        "grounding_usd": round(breakdown.get("grounding", 0.0), 6),
        "tour_total_cost_usd": round(cost.get("tour_total_cost", 0.0), 6),
        # story-retry instrumentation
        "shipped_story_count_by_stop": parsed["shipped_story_count_by_stop"],
        "attempts_by_stop": parsed["attempts_by_stop"],
        "writer_attempts_logged": parsed["writer_attempts_logged"],
        "story_retries_432": parsed["story_retries_432"],
        # gate rejections counted per arm
        "gate_235_r10": parsed["gate_235_r10"],
        "gate_472_specificity": parsed["gate_472_specificity"],
        "gate_229_contradicted": parsed["gate_229_contradicted"],
        # quality
        "score_tour": score,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return rec


def _openai_spend(summary):
    """Cumulative OpenAI (LLM) spend so far, from each cell's counted llm cost."""
    return sum((c.get("breakdown_llm_usd") or 0.0)
               for c in summary.get("cells", {}).values() if isinstance(c, dict))


def main():
    argv = sys.argv[1:]
    only_arm = argv[0] if len(argv) >= 1 else None
    only_req = argv[1] if len(argv) >= 2 else None

    summary = {
        "ticket": "LOCAL-571", "arms": ARMS,
        "requests": [{"key": k, "tour_type": t, "location": l} for k, t, l in REQUESTS],
        "stops": STOPS, "openai_budget_usd": OPENAI_BUDGET_USD,
        "gemini": "off (GEMINI_API_KEY/GOOGLE_API_KEY empty)",
        "local569_flags": "OFF in both arms", "cells": {},
    }
    if os.path.exists(SUMMARY):
        try:
            summary = json.load(open(SUMMARY))
        except Exception:
            pass
    summary.setdefault("cells", {})

    at_before = _audio_tours_count()
    summary.setdefault("audio_tours_before", at_before)
    print(f"[audio_tours BEFORE] {summary['audio_tours_before']}")

    cumulative = _openai_spend(summary)
    print(f"[cumulative OpenAI spend so far] ${cumulative:.4f}")

    # Order: arm A for all requests, then arm B — a partial run keeps a complete
    # baseline arm.
    for arm in ("A", "B"):
        if only_arm and arm != only_arm:
            continue
        for rkey, tour_type, location in REQUESTS:
            if only_req and rkey != only_req:
                continue
            cell_id = f"{rkey}_{arm}"
            if cell_id in summary["cells"] and summary["cells"][cell_id].get("ok"):
                print(f"[skip] {cell_id} already done "
                      f"(writer=${summary['cells'][cell_id].get('writer_usd', 0):.4f} "
                      f"llm=${summary['cells'][cell_id].get('breakdown_llm_usd', 0):.4f})")
                continue
            if cumulative + CELL_HEADROOM_USD > OPENAI_BUDGET_USD:
                print(f"[CAP] cumulative ${cumulative:.4f} + ${CELL_HEADROOM_USD} headroom "
                      f"would risk ${OPENAI_BUDGET_USD} cap — stopping before {cell_id}.")
                summary["stopped_at_cap"] = {"before": cell_id, "cumulative": cumulative}
                json.dump(summary, open(SUMMARY, "w"), indent=2, default=str)
                _finish(summary)
                return
            print(f"\n{'='*72}\n[RUN] {cell_id}: {location} ({tour_type})  "
                  f"writer={ARMS[arm]['TOUR_STORY_MODEL']}\n{'='*72}", flush=True)
            rec = run_cell(arm, rkey, tour_type, location)
            summary["cells"][cell_id] = rec
            cumulative += rec.get("breakdown_llm_usd", 0.0) or 0.0
            json.dump(summary, open(SUMMARY, "w"), indent=2, default=str)
            print(f"[done] {cell_id}: ok={rec['ok']} wall={rec['wall_s']}s "
                  f"stops={rec['stops_delivered']} "
                  f"writer_calls={rec['writer_calls']} writer_usd=${rec['writer_usd']:.4f} "
                  f"llm=${rec['breakdown_llm_usd']:.4f} "
                  f"retries432={rec['story_retries_432']} "
                  f"clean={rec['score_tour'].get('clean')} "
                  f"defects={rec['score_tour'].get('defects')}  "
                  f"cumulativeOpenAI=${cumulative:.4f}", flush=True)

    _finish(summary)


def _finish(summary):
    at_after = _audio_tours_count()
    summary["audio_tours_after"] = at_after
    json.dump(summary, open(SUMMARY, "w"), indent=2, default=str)
    print(f"\n[audio_tours AFTER] {at_after}")
    print(f"[cumulative OpenAI spend] ${_openai_spend(summary):.4f}")
    print(f"[summary] {SUMMARY}")


if __name__ == "__main__":
    main()
